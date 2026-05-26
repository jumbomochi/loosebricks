from pydantic import BaseModel


class BuildSuggestion(BaseModel):
    set_num: str
    name: str
    year: int
    num_parts: int
    matched_parts: int
    total_parts: int
    completeness_pct: float


class BuildSuggestResponse(BaseModel):
    items: list[BuildSuggestion]


class BuildPieceDetail(BaseModel):
    part_num: str
    color_id: int
    needed: int
    have: int


class BuildDetailResponse(BaseModel):
    set_num: str
    name: str
    year: int
    num_parts: int
    completeness_pct: float
    have: list[BuildPieceDetail]
    missing: list[BuildPieceDetail]
