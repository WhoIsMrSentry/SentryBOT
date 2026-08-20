from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class RobotAction(BaseModel):
    type: str = Field(..., description="Action category: 'servo', 'lights', 'anim', 'event', 'speak', 'buzzer', 'laser', 'stepper', 'system', 'stand', 'sit', 'home'. NEVER use 'hardware'.")
    attrs: Dict[str, Any] = Field(default_factory=dict, description="Parameters for the action (e.g., {'pan': 90} for servo)")

class SentryResponse(BaseModel):
    text: str = Field(..., min_length=1, description="MANDATORY: Your spoken response as SentryBOT (Turkish). No empty strings.")
    thoughts: str = Field(..., min_length=1, description="MANDATORY: Your internal reasoning or state evaluation.")
    actions: List[RobotAction] = Field(default_factory=list, description="List of physical or system actions to execute.")
