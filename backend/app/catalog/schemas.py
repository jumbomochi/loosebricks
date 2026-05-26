from pydantic import BaseModel


class PartResponse(BaseModel):
    part_num: str
    name: str
    category_id: int
    model_config = {"from_attributes": True}


class PartSearchResponse(BaseModel):
    items: list[PartResponse]


class ColorResponse(BaseModel):
    id: int
    name: str
    rgb: str
    is_trans: bool
    model_config = {"from_attributes": True}
