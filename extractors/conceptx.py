from .base import BaseExtractor
import torch
import torch.nn as nn
from sklearn.cluster import AgglomerativeClustering
import numpy as np
import json
import pprint

class ConceptX(nn.Module, BaseExtractor):
    def __init__(self, cfg, dataloader):
        super().__init__()
        self.cfg = cfg
        self.dataloader = dataloader
            

    def forward(self):
        ...

    @classmethod
    def code(cls):
        return "conceptx"
    
    @classmethod
    def load_from_file(cls, dataloader, path=None, cfg=None):
        """
        """
        if cfg == None:
            cfg = json.load(open(path + ".json", "r"))
        if path == None:
            path = cfg['load_path']
        pprint.pprint(cfg)
        self = cls(cfg=cfg, dataloader=dataloader)
        self.concepts = torch.tensor(torch.load("./data/conceptx_concepts.pt")).to(cfg['device'])
        return self

    @torch.no_grad()
    def activation_func(self, tokens, model, concept=None, concept_idx=None):    
        _, cache = model.run_with_cache(tokens, stop_at_layer=self.cfg["layer"]+1, names_filter=self.cfg["act_name"])
        hidden_states = cache[self.cfg["act_name"]]
    
        assert tokens.shape[1] == hidden_states.shape[1]
        
        if self.cfg['site'] == 'mlp_post':
            hidden_states = hidden_states.reshape(-1, self.cfg['d_mlp'])
        else: 
            hidden_states = hidden_states.reshape(-1, self.cfg['d_model'])
        
        
        if concept_idx == None:
            results = (hidden_states * concept).sum(-1) / (concept * concept).sum()
        else:
            results = (hidden_states * self.concepts[concept_idx, :]).sum(-1) / (concept * concept).sum()
        return results

    def extract_concepts(self, model):
        hidden_states = []
        token_num = 0
        for i in range(len(self.dataloader)):
            data = self.dataloader.get_pointer_batch().to(self.cfg["device"])
            self.dataloader.next()

            llm_outputs = model.run_with_cache(data)
            logits = llm_outputs[1][self.cfg['act_name']]  # (Batch, Token, Hidden)
            logits = logits.reshape(-1, 512)  # (B*T,H)

            if token_num + len(logits) > self.cfg["ConceptX_max_token"]:
                logits = logits[: self.cfg["ConceptX_max_token"] - token_num - len(logits)]
                hidden_states.append(logits)
                break
            token_num += len(logits)
            hidden_states.append(logits)

        hidden_states = torch.cat(hidden_states, dim=0).cpu().numpy()   #(all_token_num, 512)
        print('hidden_states.shape:',hidden_states.shape)
        clustering = AgglomerativeClustering(n_clusters=self.cfg["ConceptX_clusters"], compute_distances=True).fit(hidden_states)

        concepts = []
        
        print(clustering)
        
        labels = clustering.labels_
        print(labels)
        lengths = []
        clusters_data = []
        for i in range(self.cfg["ConceptX_clusters"]):
            indices = np.where(labels == i)[0]
            no_indices = np.where(labels != i)[0]
            concepts.append(np.mean(hidden_states[indices], axis=0))
        concepts = np.array(concepts)   
        self.concepts = torch.tensor(concepts, device=self.cfg["device"])
        torch.save(concepts, "./data/conceptx_concepts.pt")

    def get_concepts(self):
        return self.concepts
