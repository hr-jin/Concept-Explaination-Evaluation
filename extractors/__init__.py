from .ae import AutoEncoder
from .tcav import TCAVExtractor
from .conceptx import ConceptX
from .neuron import Neuron

EXTRACTORS = {
    AutoEncoder.code(): AutoEncoder,
    TCAVExtractor.code(): TCAVExtractor,
    ConceptX.code(): ConceptX
    # IntrinsicProbingExtractor.code(): IntrinsicProbingExtractor,
    Neuron.code(): Neuron,
}

def extractor_factory(cfg, dataloader):
    extractor = EXTRACTORS[cfg['extractor']]
    if cfg['load_extractor']:
        return extractor
    return extractor(cfg, dataloader).to(cfg['device'])