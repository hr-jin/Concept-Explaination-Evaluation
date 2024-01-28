from .base import BaseEvaluator

import torch
import torch.nn as nn
from logger import logger
import numpy as np

class InputTopicCoherenceEvaluator(nn.Module, BaseEvaluator):
    def __init__(
        self, 
        cfg, 
        activation_func, 
        model, 
        concept=None, 
        concept_idx=-1, 
        pmi_type='uci',
        
    ):
        nn.Module.__init__(self)
        BaseEvaluator.__init__(self, cfg, activation_func, model)
        self.concept = concept
        self.concept_idx = concept_idx
        self.pmi_type = pmi_type
        
    @classmethod
    def code(cls):
        return 'itc'
    
    def update_concept(self, concept=None, concept_idx=-1):
        self.concept = concept
        self.concept_idx = concept_idx
        
    def update_pmi_type(self, pmi_type):
        if pmi_type not in ['uci', 'umass', 'silhouette']:
            assert False, "PMI type not supported yet. please choose from: ['uci', 'umass', 'silhouette']."
        self.pmi_type = pmi_type
        
    
    def get_metric(self, eval_tokens):
        most_critical_tokens, most_critical_token_idxs = self.get_most_critical_tokens(eval_tokens, self.concept, self.concept_idx)
        most_critical_token_idxs = most_critical_token_idxs[most_critical_tokens != '\ufffd']
        most_critical_tokens = most_critical_tokens[most_critical_tokens != '\ufffd']
        if most_critical_tokens.shape[0] == 1:
            most_critical_tokens = np.repeat(most_critical_tokens, 2)
            most_critical_token_idxs = np.repeat(most_critical_token_idxs, 2)
        sentences = np.array(self.model.to_string(eval_tokens[:,1:]))
        inclusion = torch.tensor([[token in sentence.lower() for sentence in sentences] for token in most_critical_tokens]).to(int)
        epsilon=1e-10
        corpus_len = sentences.shape[0]
        binary_inclusion = inclusion @ inclusion.T / corpus_len
        token_inclusion = inclusion.sum(-1) / corpus_len
        token_inclusion_mult = token_inclusion.unsqueeze(0).T @ token_inclusion.unsqueeze(0)
        if self.pmi_type == 'uci':  
            pmis = torch.log((binary_inclusion + epsilon) / token_inclusion_mult)
            mask = torch.triu(torch.ones_like(pmis),diagonal=1)
            final_pmi = (pmis * mask).sum() / mask.sum()
        elif self.pmi_type == 'umass':
            pmis = torch.log((binary_inclusion + epsilon) / token_inclusion)
            mask = torch.triu(torch.ones_like(pmis),diagonal=1)
            final_pmi = (pmis * mask).sum() / mask.sum()
        elif self.pmi_type == 'silhouette':
            best_num, best_score = self.get_silhouette_score(np.array(most_critical_token_idxs))
            final_pmi = best_score / best_num
        else:
            assert False, "PMI type not supported yet. please choose from: ['uci', 'umass', 'silhouette']."
        
        logger.info('Input Topic Coherence Metric ({}): {:.4f}'.format(self.pmi_type, final_pmi))    
        return final_pmi
        
            