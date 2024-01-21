import argparse
from utils import *
from config import cfg as default_cfg
import logging
from dataloaders import dataloader_factory
from extractors import extractor_factory
from datasets_ import dataset_factory
from models import model_factory
from evaluators import evaluator_factory
import json

def main():
    """
    Here we take the process of concept extraction by autoencoder as an example.
    """
    
    logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO, force=True)
    logger = logging.getLogger('logger')

    parser = argparse.ArgumentParser()
    cfg, args = arg_parse_update_cfg(default_cfg, parser)

    model = model_factory(cfg)
    
    logger.info('loaded model...')
    
    cfg = process_cfg(cfg, model)
    print(json.dumps(cfg, indent=2))
    
    train_data = dataset_factory(cfg)
    dataloader = dataloader_factory(cfg, train_data, model)
    extractor = extractor_factory(cfg, dataloader)
    if cfg['load_extractor']:
        logger.info('loading extractor...')
        extractor = extractor.load_from_file(dataloader, cfg['load_path'], cfg).to(cfg['device'])
    else:
        logger.info('extract concepts...')
        extractor.extract_concepts(model)
        
    concepts = extractor.get_concepts()
    print('concept vectors:', concepts)
        
    evaluator = evaluator_factory(cfg, extractor.activation_func, model)
    token_list = []
    
    for i in range(1):
        tokens = dataloader.get_processed_batch()
        token_list.append(tokens)
    tokens = torch.cat(token_list, 0)
    evaluator.get_most_critical_tokens(tokens, concept_idx=2919)
    
    
if __name__ == "__main__":
    main()