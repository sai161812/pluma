"""Bounded local health and exact self-recovery requests."""
from typing import Literal
from uuid import UUID
from pydantic import BaseModel,ConfigDict,StrictStr,StrictBool,StrictInt,Field,model_validator


class HealthRequest(BaseModel):
    model_config=ConfigDict(extra="forbid",strict=True)
    protocol_version:Literal[1]
    message_type:Literal["health_query","setup_check","core_restart","core_shutdown"]
    request_id:StrictStr
    instance_id:StrictStr|None=None
    pid:StrictInt|None=Field(default=None,gt=0)
    creation_time:StrictInt|None=Field(default=None,gt=0)
    include_microphone:StrictBool|None=None

    @model_validator(mode="before")
    @classmethod
    def integer_version(cls,value):
        if not isinstance(value,dict) or type(value.get("protocol_version")) is not int:
            raise ValueError("Invalid protocol version type.")
        return value

    @model_validator(mode="after")
    def valid(self):
        for value in (self.request_id,self.instance_id):
            if value is not None and str(UUID(value))!=value:raise ValueError("Invalid identity.")
        supplied=self.model_fields_set-{"protocol_version","message_type","request_id"}
        required={"health_query":set(),"setup_check":{"instance_id","include_microphone"},
                  "core_restart":{"instance_id","pid","creation_time"},
                  "core_shutdown":{"instance_id","pid","creation_time"}}[self.message_type]
        if supplied!=required or any(getattr(self,key) is None for key in required):raise ValueError("Unexpected health material.")
        return self
