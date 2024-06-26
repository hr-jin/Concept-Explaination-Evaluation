from abc import *
import torch
import numpy as np
import pandas as pd
from tqdm import tqdm
from logger import logger
from functools import partial
from sklearn.cluster import KMeans
from sklearn import metrics
from utils import *
import torch.nn.functional as F

class BaseEvaluator(metaclass=ABCMeta):
    def __init__(
        self, 
        cfg, 
        activation_func, 
        model
    ):
        super().__init__()
        self.activation_func = activation_func
        self.cfg = cfg
        self.model = model

    @classmethod
    @abstractmethod
    def code(cls):
        pass
    
    @torch.no_grad()
    def get_hidden_states(
        self, 
        tokens
    ):
        _, cache = self.model.run_with_cache(tokens, stop_at_layer=self.cfg["layer"]+1, names_filter=self.cfg["act_name"])
        hidden_states = cache[self.cfg["act_name"]]
        return hidden_states
    
    @abstractmethod
    def get_metric():
        pass
    
    @abstractmethod
    def update_concept(self):
        pass
    
    @staticmethod
    def ablation_hook(
        hidden_states, 
        hook, 
        activations,
        concept, 
    ):
        output = hidden_states - (activations.squeeze().unsqueeze(1) @ concept.unsqueeze(0)).reshape(hidden_states.shape)
        return output
    
    @staticmethod
    def replacement_hook(
        hidden_states, 
        hook, 
        concept, 
    ):
        origin_mean = hidden_states.mean(dim=-1, keepdim=True)
        origin_std = hidden_states.std(dim=-1, keepdim=True)
        concept_renormed = (concept - concept.mean(dim=-1, keepdim=True)) / concept.std(dim=-1, keepdim=True)
        output = concept_renormed * origin_std + origin_mean
        return output
    
    def get_loss_diff(
        self, 
        tokens, 
        concept, 
        hook,
        concept_act,
    ):
        loss = self.model.run_with_hooks(
            tokens, 
            return_type='loss',
            loss_per_token=True
        )
        
        loss_disturbed = self.model.run_with_hooks(
            tokens, 
            return_type='loss', 
            loss_per_token=True,
            fwd_hooks=[(
                self.cfg["act_name"], 
                partial(hook, concept=concept,activations=concept_act)
            )]
        )
        return (loss_disturbed - loss).cpu().numpy()
    
    def get_class_logit_diff(
        self, 
        tokens, 
        concept, 
        class_idx, 
        hook,
        concept_act,
    ):
        # class_idx = -1 means the next token's idx
        logits = self.model.run_with_hooks(tokens)
        logits_disturbed = self.model.run_with_hooks(
            tokens, 
            fwd_hooks=[(
                self.cfg["act_name"], 
                partial(hook, concept=concept,activations=concept_act))
            ]
        )
        logits = logits[:,:-1,:]
        logits_disturbed = logits_disturbed[:,:-1,:]
        
        if class_idx == -1:
            max_indices = torch.argmax(logits, dim=-1)
            logit = torch.gather(logits, dim=-1, index=max_indices.unsqueeze(-1)).squeeze()
            logit_disturbed = torch.gather(logits_disturbed, dim=-1, index=max_indices.unsqueeze(-1)).squeeze()
        elif class_idx == -2:
            true_next_indices = tokens[:,1:].clone().detach().to(self.cfg['device'])
            logit = torch.gather(logits, dim=-1, index=true_next_indices.unsqueeze(-1)).squeeze()

            logit_disturbed = torch.gather(logits_disturbed, dim=-1, index=true_next_indices.unsqueeze(-1)).squeeze()
        else:
            logit = logits[:,:,class_idx]
            logit_disturbed = logits_disturbed[:,:,class_idx]
        
        
        return (logit_disturbed - logit).cpu().numpy()
    
    def get_loss_gradient(self, tokens):
        _, cache = self.model.run_with_cache(
            tokens, 
            return_type='loss', 
            incl_bwd=True, 
            names_filter=self.cfg["act_name"]
        )
        grad = cache[self.cfg['act_name']+'_grad'].cpu().numpy()
        hidden_state = cache[self.cfg['act_name']].cpu().numpy()
        return grad, hidden_state
    
    def get_class_logit_gradient(self, tokens, class_idx, concept_act):
        grads = []
        hidden_states = []
        _, cache = run_with_cache_top1logit_bkwd(
            tokens=tokens, 
            model=self.model,
            names_filter=[self.cfg['act_name']], 
            logit_token_idx=class_idx,
            concept_act=concept_act,
            cfg=self.cfg,
        )
        grads.append(cache[self.cfg['act_name']+'_grad'].cpu().numpy())
        hidden_states.append(cache[self.cfg['act_name']].cpu().numpy())
        grad = np.array(grads)[0]
        hidden_state = np.array(hidden_states)[0]
        return grad, hidden_state

    
    def get_topic_coherence(self, eval_tokens, most_critical_tokens):
        if most_critical_tokens.shape[0] == 0:
            topic_coherence = -20.
        else:
            sentences = np.array(self.model.to_string(eval_tokens[:,1:]))
            inclusion = torch.tensor([[token in sentence.lower() for sentence in sentences] for token in most_critical_tokens]).to(int)
            epsilon=1e-10
            corpus_len = sentences.shape[0]
            binary_inclusion = inclusion @ inclusion.T / corpus_len
            token_inclusion = inclusion.sum(-1) / corpus_len
            if self.pmi_type == 'uci':  
                token_inclusion_mult = token_inclusion.unsqueeze(0).T @ token_inclusion.unsqueeze(0)
                pmis = torch.log((binary_inclusion + epsilon) / token_inclusion_mult)
                mask = torch.triu(torch.ones_like(pmis),diagonal=1)
                topic_coherence = (pmis * mask).sum() / mask.sum()
            elif self.pmi_type == 'umass':  
                pmis = torch.log((binary_inclusion + epsilon) / token_inclusion)
                mask = torch.ones_like(pmis) - torch.eye(pmis.shape[0])
                topic_coherence = (pmis * mask).sum() / mask.sum()
        return topic_coherence
    
    def get_emb_topic_coherence(self, most_critical_token_idxs):
        X = self.model.embed.W_E.detach().cpu()[most_critical_token_idxs]
        if self.pmi_type == 'emb_dist':  
            pmis = torch.tensor([[(emb1 - emb2).square().sum(-1).sqrt() for emb2 in X] for emb1 in X])
            if X.shape[0] == 1:
                topic_coherence = 0.
            elif X.shape[0] == 0:
                topic_coherence = -2.
            else:
                mask = torch.triu(torch.ones_like(pmis),diagonal=1)
                topic_coherence = (pmis * mask).sum() / mask.sum()
        elif self.pmi_type == 'emb_cos':  
            X_normed = X / X.square().sum(-1).sqrt().unsqueeze(1)
            if X.shape[0] == 1:
                topic_coherence = 1.
            elif X.shape[0] == 0:
                topic_coherence = -1.
            else:
                pmis = X_normed @ X_normed.T
                mask = torch.triu(torch.ones_like(pmis),diagonal=1)
                topic_coherence = (pmis * mask).sum() / mask.sum()
        return topic_coherence
        
    
    def get_logit_distribution_corr(
        self, 
        tokens, 
        concept, 
        hook, 
        topk=None, 
        corr_func='pearson',
        concept_act=None,
    ):
        origin_logits = self.model.run_with_hooks(tokens)
        disturbed_logits = self.model.run_with_hooks(
            tokens, 
            fwd_hooks=[(
                self.cfg["act_name"], 
                partial(hook, concept=concept,activations=concept_act)
                )]
        )
        if topk != None:
            origin_values, origin_indices = torch.topk(
                origin_logits, 
                k=topk, 
                dim=-1, 
                sorted=True
            )
            disturbed_values = disturbed_logits.gather(-1, origin_indices)
        else:
            origin_values = origin_logits
            disturbed_values = disturbed_logits
            
        
        distributed_softmax = torch.softmax(disturbed_values, dim=-1) + 1e-10
        origin_softmax = torch.softmax(origin_values, dim=-1) + 1e-10
        if corr_func == 'pearson':
            corr = torch.cosine_similarity(
                distributed_softmax - distributed_softmax.mean(-1, keepdim=True), 
                origin_softmax - origin_softmax.mean(-1, keepdim=True), 
                dim=-1
            )
        elif corr_func == 'KL_div':
            corr = -F.kl_div(distributed_softmax.log(), origin_softmax, reduction='none').sum(-1)
        elif corr_func == 'openai_var':
            corr = 1 - (distributed_softmax - origin_softmax).square().mean(-1) / torch.var(origin_softmax, dim=-1)
        else:
            assert False, "Correlation type not supported yet. please choose from: ['pearson', 'KL_div', 'openai_var']."
        return corr.cpu().numpy()
    
    def get_preferred_predictions_of_concept(
        self, 
        tokens, 
        concept,
    ):
        logits = self.model.run_with_hooks(
            tokens[:2], 
            fwd_hooks=[(
                self.cfg["act_name"], 
                partial(self.replacement_hook, concept=concept)
            )]
        )[0][0]
        top_logits, topk_indices = torch.topk(logits, k=self.cfg['topic_len'], dim=0, sorted=True)
        most_preferred_tokens = np.array([
            token.strip().lower() 
            for token in self.model.to_str_tokens(topk_indices)
        ])
        return top_logits, most_preferred_tokens, topk_indices.detach().cpu().numpy()
    
    def get_silhouette_score(self, token_indices):
        token_indices_unique = np.unique(token_indices)
        X = self.model.embed.W_E.detach().cpu().numpy()[token_indices]
        X_unique = self.model.embed.W_E.detach().cpu().numpy()[token_indices_unique]
        if X_unique.shape[0] == 0:
            best_num = 1. 
            best_score = 2. - X_unique.shape[0]
        elif X_unique.shape[0] in [1, 2]:
            best_num = X_unique.shape[0]
            best_score = 2. - X_unique.shape[0]
        else:
            N_clusters = range(2, min(6, X.shape[0]))
            best_num = 1.
            best_score = -2.
            for num in N_clusters:
                kmeans_model = KMeans(n_clusters=num, random_state=0, n_init='auto').fit(X)
                labels = kmeans_model.labels_
                silhouette_score = metrics.silhouette_score(X, labels)
                logger.info('Number of clusters: {}, silhouette score: {:.4f}'.format(
                    num, silhouette_score))
                if silhouette_score > best_score:
                    best_score = silhouette_score
                    best_num = num
        logger.info('Best number of clusters: {}, best silhouette score: {:.4f}'.format(best_num, best_score))
        return best_num, best_score
    
    def get_most_critical_tokens(self, eval_tokens, concept=None, concept_idx=-1):   
             
        _, maxlen = eval_tokens.shape[0], eval_tokens.shape[1]
        minibatch = self.cfg['concept_eval_batchsize']
        eval_tokens = eval_tokens.split(minibatch, dim=0)
            
        results = []
        for tokens in tqdm(eval_tokens, desc='Searching the corpus for the most critical token for the current concept'):
            num_tokens = tokens.shape[0] * maxlen
            concept_acts = self.activation_func(tokens, self.model, concept, concept_idx) # minibatch * maxlen
            origin_acts = concept_acts # minibatch * maxlen
            
            print('concept_acts.shape:',concept_acts.shape)

            most_imp_actis = np.zeros([num_tokens])
            most_imp_pos = np.zeros([num_tokens])
            most_imp_tokens = np.zeros([num_tokens])
            imp_this_token = np.zeros([num_tokens])

            padding_id = self.model.tokenizer.unk_token_id
            for padding_position in range(maxlen):
                tmp_tokens = tokens.clone()
                tmp_tokens[:,padding_position] = padding_id
                concept_acts = self.activation_func(tmp_tokens, self.model, concept, concept_idx) # minibatch * maxlen
                
                acti_diff = origin_acts - concept_acts
                acti_diff = acti_diff.detach().cpu().numpy()

                mask = np.ones((tokens.shape[0], maxlen))
                mask[:, padding_position] = 0
                mask = mask.reshape((tokens.shape[0] * maxlen))
                imp_this_token = np.where(mask == 0, acti_diff , imp_this_token)
                
                acti_diff =  acti_diff * mask
                
                now_pos = np.array([padding_position for _ in range(tokens.shape[0] * maxlen)])
                padding_token_id = np.tile(tokens[:,padding_position].unsqueeze(1).cpu().numpy(), [1, maxlen])
                padding_token_id = padding_token_id.reshape((tokens.shape[0] * maxlen))

                indices = most_imp_actis > acti_diff
                most_imp_pos = np.where(indices, most_imp_pos , now_pos)
                most_imp_tokens = np.where(indices, most_imp_tokens , padding_token_id)
                most_imp_actis = np.where(indices, most_imp_actis , acti_diff)

            tokens_reshaped = tokens.reshape((-1)).cpu().numpy()
            df = pd.DataFrame(data=self.model.to_str_tokens(tokens_reshaped.astype(np.int32)), columns=["token"])
            df_ctxt = pd.DataFrame(data=self.model.to_str_tokens(most_imp_tokens.astype(np.int32)), columns=["token"])
            
            df["token_idx"] = tokens_reshaped
            df_ctxt["token_idx"] = most_imp_tokens
            df["imp"] = imp_this_token
            df_ctxt["imp"] = most_imp_actis
            df_agg = df.groupby('token').agg('max').sort_values(by=['imp'],ascending=False)
            df_ctxt_agg = df_ctxt.groupby('token').agg('max').sort_values(by=['imp'],ascending=False)

            result = pd.concat([df_agg, df_ctxt_agg]).sort_values(by=['imp'],ascending=False).reset_index()
            result = result.drop_duplicates(subset=['token'])
            results.append(result[:50])
        
        df_final = pd.concat(results).groupby('token').agg('max').sort_values(by=['imp'],ascending=False).reset_index()[['token','imp','token_idx']]
        df_final_show = df_final[:self.cfg['topic_len']]
        df_final_show['token'] = df_final_show['token'].apply(lambda x:repr(x))
        print('df_final:\n', df_final_show)
        df_final = df_final[:self.cfg['topic_len']]
        origin_df = df_final
        df_most_critical_tokens = df_final['token'].apply(lambda x:x.lower()).values
        
        stripped_critical_tokens = np.array([t.strip() for t in df_most_critical_tokens])
        df_most_critical_token_idxs = df_final['token_idx'].astype('int32').values
        most_critical_token_idxs = df_most_critical_token_idxs.astype('int32')
        most_critical_tokens = np.where(stripped_critical_tokens != '', stripped_critical_tokens, df_most_critical_tokens)
        logger.info('The most critical tokens(after removing the spaces and changing to lower case): \n{}'.format(' '.join([repr(t) for t in most_critical_tokens])))
        return most_critical_tokens, most_critical_token_idxs, origin_df, df_most_critical_token_idxs