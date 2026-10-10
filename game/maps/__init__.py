"""Map generator registry.  Every map implements :class:`BaseMapGenerator`."""
from .generator import BaseMapGenerator, GenerationError, MapData
from .research_station import ResearchStationGenerator
from .mining_complex import MiningComplexGenerator

MAP_REGISTRY = {
    ResearchStationGenerator.map_id: ResearchStationGenerator,
    MiningComplexGenerator.map_id: MiningComplexGenerator,
    # Future maps register here (Flooded Facility, Desert Complex, Spaceport ...)
}
DEFAULT_MAP = ResearchStationGenerator.map_id


def get_generator(map_id: str = DEFAULT_MAP) -> BaseMapGenerator:
    try:
        return MAP_REGISTRY[map_id]()
    except KeyError:
        raise GenerationError(f"unknown map '{map_id}'")


def generate_map(seed: int, map_id: str = DEFAULT_MAP) -> MapData:
    return get_generator(map_id).generate(seed)


__all__ = ["MAP_REGISTRY", "DEFAULT_MAP", "get_generator", "generate_map", "MapData", "GenerationError", "BaseMapGenerator"]
