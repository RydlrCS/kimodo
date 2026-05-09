"""
Card 2: Service Contracts (Pydantic Schemas)

Defines strict request/response contracts for:
1. Qwen Planner API (story prompt → validated motion script)
2. Kimodo Generator API (motion script → motion generation)

All schemas include defensive validation, error codes, and examples.
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
import json


# ============================================================================
# Enums
# ============================================================================

class TransitionPolicy(str, Enum):
    """How to transition between motion segments."""
    SMOOTH = "smooth"  # Blend final frame of A with initial frame of B
    CUT = "cut"  # Hard cut from A to B
    HOLD = "hold"  # Hold final pose of A before B starts
    OVERLAP = "overlap"  # Overlap A and B for N frames


class ConstraintType(str, Enum):
    """Types of kinematic constraints."""
    POSITIONAL = "positional"  # XYZ position constraints
    ROTATIONAL = "rotational"  # Joint angle constraints
    VELOCITY = "velocity"  # Movement speed limits
    CONTACT = "contact"  # Foot contact, hand placement
    NONE = "none"


# ============================================================================
# Planner API Schemas (Qwen LLM → Motion Script)
# ============================================================================

class CharacterDefinition(BaseModel):
    """Definition of a character in the scene."""
    
    character_id: str = Field(
        ...,
        min_length=1,
        max_length=50,
        pattern="^[a-zA-Z0-9_-]+$",
        description="Unique identifier for this character (alphanumeric + _ -)."
    )
    
    skeleton_type: str = Field(
        default="soma",
        description="Skeleton rig type (soma, g1, smpl-x, etc.)"
    )
    
    description: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Brief character description (e.g., 'tall female dancer')."
    )
    
    @field_validator("character_id")
    @classmethod
    def validate_char_id(cls, v):
        if not v or len(v) > 50:
            raise ValueError("character_id must be 1-50 chars")
        return v.strip()


class MotionSegment(BaseModel):
    """A single motion segment for one character."""
    
    segment_id: int = Field(
        ...,
        ge=0,
        description="Sequence order (0-based) within character's script."
    )
    
    action_text: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Natural language action description (e.g., 'walk forward with arms raised')."
    )
    
    duration_sec: float = Field(
        default=2.0,
        ge=0.5,
        le=30.0,
        description="Duration of this motion segment in seconds (0.5-30s)."
    )
    
    transition_policy: TransitionPolicy = Field(
        default=TransitionPolicy.SMOOTH,
        description="How to transition to the next segment."
    )
    
    interaction_target: Optional[str] = Field(
        default=None,
        description="Another character_id to interact with (optional)."
    )
    
    constraints: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Kinematic constraints dict (e.g., {'floor_contact': True})."
    )
    
    @field_validator("action_text")
    @classmethod
    def validate_action_text(cls, v):
        if not v or len(v) < 3:
            raise ValueError("action_text must be >= 3 chars")
        return v.strip()
    
    @field_validator("duration_sec")
    @classmethod
    def validate_duration(cls, v):
        if not (0.5 <= v <= 30.0):
            raise ValueError("duration_sec must be between 0.5 and 30.0 seconds")
        return v


class PlannerRequest(BaseModel):
    """Request from frontend to Qwen planner."""
    
    scene_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Unique identifier for this scene/request."
    )
    
    user_prompt: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="High-level story or interaction prompt from user (10-2000 chars)."
    )
    
    characters: List[CharacterDefinition] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="List of characters in the scene (1-10 characters)."
    )
    
    duration_limit_sec: float = Field(
        default=60.0,
        ge=10.0,
        le=600.0,
        description="Maximum total duration for the scene (10-600 seconds)."
    )
    
    interactive_mode: bool = Field(
        default=False,
        description="If True, planner may request user input for interactions."
    )
    
    @field_validator("scene_id")
    @classmethod
    def validate_scene_id(cls, v):
        if not v or len(v) > 100:
            raise ValueError("scene_id must be 1-100 chars")
        return v.strip()
    
    @field_validator("user_prompt")
    @classmethod
    def validate_prompt(cls, v):
        if not v or len(v) < 10:
            raise ValueError("user_prompt must be >= 10 chars")
        return v.strip()
    
    @field_validator("characters")
    @classmethod
    def validate_characters(cls, v):
        if not v or len(v) > 10:
            raise ValueError("Must have 1-10 characters")
        # Check for duplicate character_ids
        ids = [c.character_id for c in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate character_id found")
        return v


class PlannerResponse(BaseModel):
    """Response from Qwen planner (validated motion script)."""
    
    scene_id: str = Field(
        ...,
        description="Echo of request scene_id."
    )
    
    status: str = Field(
        default="success",
        description="Planner status (success/partial/error).",
        json_schema_extra={"enum": ["success", "partial", "error"]}
    )
    
    error_message: Optional[str] = Field(
        default=None,
        description="Error details if status != success."
    )
    
    scripts: Dict[str, List[MotionSegment]] = Field(
        default_factory=dict,
        description="Per-character motion scripts: {character_id: [segments]}."
    )
    
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional metadata (model name, version, timestamp, etc.)."
    )
    
    total_duration_sec: float = Field(
        default=0.0,
        ge=0.0,
        description="Computed total duration of all characters combined."
    )
    
    @field_validator("total_duration_sec")
    @classmethod
    def validate_total_duration(cls, v):
        if v < 0:
            raise ValueError("total_duration_sec must be non-negative")
        return v


# ============================================================================
# Generator API Schemas (Motion Script → Kimodo Generation)
# ============================================================================

class GenerationConstraint(BaseModel):
    """Per-character generation constraint."""
    
    constraint_type: ConstraintType = Field(
        default=ConstraintType.NONE,
        description="Type of constraint to apply."
    )
    
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Constraint-specific parameters (e.g., target position, velocity limit)."
    )
    
    priority: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Priority level (1-10, higher = enforced more strictly)."
    )


class CharacterGenerationState(BaseModel):
    """Per-character state for generation."""
    
    character_id: str = Field(
        ...,
        description="Character identifier."
    )
    
    skeleton_type: str = Field(
        default="soma",
        description="Skeleton rig type."
    )
    
    segments: List[MotionSegment] = Field(
        ...,
        description="Motion segments for this character."
    )
    
    initial_pose: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional initial pose (joint angles or transformation)."
    )
    
    constraints: Optional[List[GenerationConstraint]] = Field(
        default=None,
        description="List of kinematic constraints."
    )
    
    @field_validator("character_id")
    @classmethod
    def validate_id(cls, v):
        if not v:
            raise ValueError("character_id required")
        return v.strip()


class GeneratorRequest(BaseModel):
    """Request to Kimodo generator (from planner response)."""
    
    scene_id: str = Field(
        ...,
        description="Scene identifier."
    )
    
    characters: List[CharacterGenerationState] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Character states and motion segments."
    )
    
    seed: int = Field(
        default=42,
        ge=0,
        description="Random seed for deterministic generation."
    )
    
    num_samples: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Number of motion samples to generate (1-5)."
    )
    
    device: Optional[str] = Field(
        default=None,
        description="Compute device (cuda, rocm, cpu). If None, auto-detect."
    )
    
    @field_validator("characters")
    @classmethod
    def validate_chars(cls, v):
        if not v or len(v) > 10:
            raise ValueError("Must have 1-10 characters")
        return v


class MotionOutput(BaseModel):
    """Generated motion output for a single character."""
    
    character_id: str = Field(
        ...,
        description="Character identifier."
    )
    
    motion_data: Dict[str, Any] = Field(
        ...,
        description="Motion data (NPZ converted to dict: posed_joints, rotation_mats, foot_contacts, etc.)."
    )
    
    duration_sec: float = Field(
        default=0.0,
        description="Actual duration of generated motion."
    )
    
    frame_count: int = Field(
        default=0,
        description="Number of frames in motion."
    )
    
    fps: int = Field(
        default=30,
        description="Frames per second."
    )
    
    quality_score: Optional[float] = Field(
        default=None,
        description="Optional quality metric (0-1)."
    )


class GeneratorResponse(BaseModel):
    """Response from Kimodo generator."""
    
    scene_id: str = Field(
        ...,
        description="Scene identifier."
    )
    
    status: str = Field(
        default="success",
        description="Generation status.",
        json_schema_extra={"enum": ["success", "partial", "error"]}
    )
    
    error_message: Optional[str] = Field(
        default=None,
        description="Error details if status != success."
    )
    
    motions: List[MotionOutput] = Field(
        default_factory=list,
        description="Generated motions per character."
    )
    
    total_frames: int = Field(
        default=0,
        description="Total frames across all characters."
    )
    
    generation_time_sec: float = Field(
        default=0.0,
        description="Wall-clock time to generate (seconds)."
    )
    
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata (model version, device, seed, etc.)."
    )


# ============================================================================
# Validation Examples
# ============================================================================

def example_planner_request() -> PlannerRequest:
    """Example valid planner request."""
    return PlannerRequest(
        scene_id="scene_001",
        user_prompt="Two dancers interact in the middle of a stage, one leads a waltz while the other follows.",
        characters=[
            CharacterDefinition(character_id="dancer1", skeleton_type="soma", description="Lead dancer"),
            CharacterDefinition(character_id="dancer2", skeleton_type="soma", description="Follow dancer"),
        ],
        duration_limit_sec=60.0,
        interactive_mode=False
    )


def example_planner_response() -> PlannerResponse:
    """Example valid planner response."""
    return PlannerResponse(
        scene_id="scene_001",
        status="success",
        scripts={
            "dancer1": [
                MotionSegment(
                    segment_id=0,
                    action_text="Walk forward with arms extended in waltz position",
                    duration_sec=5.0,
                    transition_policy=TransitionPolicy.SMOOTH,
                    interaction_target="dancer2"
                ),
                MotionSegment(
                    segment_id=1,
                    action_text="Turn left while leading dancer2 in circular motion",
                    duration_sec=5.0,
                    transition_policy=TransitionPolicy.SMOOTH
                ),
            ],
            "dancer2": [
                MotionSegment(
                    segment_id=0,
                    action_text="Follow dancer1 with arms extended, matching their tempo",
                    duration_sec=5.0,
                    transition_policy=TransitionPolicy.SMOOTH,
                    interaction_target="dancer1"
                ),
                MotionSegment(
                    segment_id=1,
                    action_text="Turn right while being led by dancer1",
                    duration_sec=5.0,
                    transition_policy=TransitionPolicy.SMOOTH
                ),
            ]
        },
        metadata={"model": "Qwen2.5-7B-Instruct", "created_at": "2026-05-09T12:00:00Z"},
        total_duration_sec=10.0
    )


def example_generator_request() -> GeneratorRequest:
    """Example valid generator request."""
    planner_resp = example_planner_response()
    resp_dict = planner_resp.model_dump()
    
    chars = [
        CharacterGenerationState(
            character_id="dancer1",
            skeleton_type="soma",
            segments=resp_dict["scripts"]["dancer1"]
        ),
        CharacterGenerationState(
            character_id="dancer2",
            skeleton_type="soma",
            segments=resp_dict["scripts"]["dancer2"]
        ),
    ]
    
    return GeneratorRequest(
        scene_id="scene_001",
        characters=chars,
        seed=42,
        num_samples=1
    )


# ============================================================================
# Test & Validation Functions
# ============================================================================

def validate_schema_examples():
    """Test all schemas with valid and invalid payloads."""
    
    print("=== Card 2: Schema Validation Tests ===\n")
    
    # Test 1: Valid Planner Request
    try:
        req = example_planner_request()
        print("✓ Valid Planner Request: PASS")
    except Exception as e:
        print(f"✗ Valid Planner Request: FAIL - {e}")
    
    # Test 2: Valid Planner Response
    try:
        resp = example_planner_response()
        print("✓ Valid Planner Response: PASS")
    except Exception as e:
        print(f"✗ Valid Planner Response: FAIL - {e}")
    
    # Test 3: Valid Generator Request
    try:
        req = example_generator_request()
        print("✓ Valid Generator Request: PASS")
    except Exception as e:
        print(f"✗ Valid Generator Request: FAIL - {e}")
    
    print()
    
    # Test 4: Invalid Planner Request (missing required field)
    try:
        PlannerRequest(
            scene_id="test",
            # Missing user_prompt - should fail
            characters=[
                CharacterDefinition(character_id="c1")
            ]
        )
        print("✗ Invalid Request (missing user_prompt): FAIL - should have raised error")
    except Exception as e:
        print("✓ Invalid Request (missing user_prompt): PASS - correctly rejected")
    
    # Test 5: Invalid Planner Request (user_prompt too short)
    try:
        PlannerRequest(
            scene_id="test",
            user_prompt="short",  # < 10 chars
            characters=[
                CharacterDefinition(character_id="c1")
            ]
        )
        print("✗ Invalid Request (short prompt): FAIL - should have raised error")
    except Exception as e:
        print("✓ Invalid Request (short prompt): PASS - correctly rejected")
    
    # Test 6: Invalid character_id (special chars not allowed)
    try:
        CharacterDefinition(character_id="c1@invalid")
        print("✗ Invalid character_id: FAIL - should have raised error")
    except Exception as e:
        print("✓ Invalid character_id: PASS - correctly rejected")
    
    # Test 7: Invalid duration_sec (out of range)
    try:
        MotionSegment(
            segment_id=0,
            action_text="test action",
            duration_sec=60.0  # > 30.0 max
        )
        print("✗ Invalid duration_sec: FAIL - should have raised error")
    except Exception as e:
        print("✓ Invalid duration_sec: PASS - correctly rejected")
    
    # Test 8: Duplicate character_ids
    try:
        PlannerRequest(
            scene_id="test",
            user_prompt="this is a long enough prompt",
            characters=[
                CharacterDefinition(character_id="char1"),
                CharacterDefinition(character_id="char1"),  # Duplicate
            ]
        )
        print("✗ Duplicate character_ids: FAIL - should have raised error")
    except Exception as e:
        print("✓ Duplicate character_ids: PASS - correctly rejected")
    
    print()
    print("=== All Schema Tests Complete ===")


if __name__ == "__main__":
    validate_schema_examples()
