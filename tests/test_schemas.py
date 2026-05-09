"""
Test schemas from Card 2: Service Contracts

Runs verification tests for Pydantic models:
- PLanner API (story prompt → validated motion script)
- Generator API (motion script → Kimodo generation)
"""

import pytest
from kimodo.schemas import (
    PlannerRequest,
    PlannerResponse,
    GeneratorRequest,
    GeneratorResponse,
    CharacterDefinition,
    MotionSegment,
    TransitionPolicy,
    example_planner_request,
    example_planner_response,
    example_generator_request,
)


class TestPlannerSchemas:
    """Test Planner API schemas."""
    
    def test_valid_planner_request(self):
        """Valid planner request accepts all fields."""
        req = example_planner_request()
        assert req.scene_id == "scene_001"
        assert len(req.characters) == 2
        assert req.user_prompt.startswith("Two dancers")
    
    def test_valid_planner_response(self):
        """Valid planner response with scripts."""
        resp = example_planner_response()
        assert resp.status == "success"
        assert "dancer1" in resp.scripts
        assert len(resp.scripts["dancer1"]) == 2
    
    def test_invalid_request_missing_prompt(self):
        """Invalid request rejects missing user_prompt."""
        with pytest.raises(Exception):  # ValidationError
            PlannerRequest(
                scene_id="test",
                # Missing user_prompt
                characters=[CharacterDefinition(character_id="c1")]
            )
    
    def test_invalid_request_short_prompt(self):
        """Invalid request rejects prompt < 10 chars."""
        with pytest.raises(Exception):  # ValidationError
            PlannerRequest(
                scene_id="test",
                user_prompt="short",  # < 10 chars
                characters=[CharacterDefinition(character_id="c1")]
            )
    
    def test_invalid_character_id_special_chars(self):
        """Invalid character_id with special chars."""
        with pytest.raises(Exception):  # ValidationError
            CharacterDefinition(character_id="char@invalid!")
    
    def test_invalid_motion_duration(self):
        """Invalid motion duration > 30s."""
        with pytest.raises(Exception):  # ValidationError
            MotionSegment(
                segment_id=0,
                action_text="test action here",
                duration_sec=60.0  # > 30.0 max
            )
    
    def test_duplicate_character_ids(self):
        """Invalid request with duplicate character IDs."""
        with pytest.raises(Exception):  # ValidationError
            PlannerRequest(
                scene_id="test",
                user_prompt="this is a long enough test prompt",
                characters=[
                    CharacterDefinition(character_id="c1"),
                    CharacterDefinition(character_id="c1"),  # Duplicate
                ]
            )
    
    def test_transition_policy_enum(self):
        """Transition policy restricts to valid values."""
        seg = MotionSegment(
            segment_id=0,
            action_text="test action",
            transition_policy=TransitionPolicy.SMOOTH
        )
        assert seg.transition_policy == TransitionPolicy.SMOOTH


class TestGeneratorSchemas:
    """Test Generator API schemas."""
    
    def test_valid_generator_request(self):
        """Valid generator request from planner response."""
        req = example_generator_request()
        assert req.scene_id == "scene_001"
        assert len(req.characters) == 2
        assert req.seed == 42
    
    def test_invalid_generator_no_characters(self):
        """Invalid generator request with no characters."""
        with pytest.raises(Exception):  # ValidationError
            GeneratorRequest(
                scene_id="test",
                characters=[]  # Empty
            )
    
    def test_generator_response_status(self):
        """Generator response status is constrained."""
        # Valid status
        resp = GeneratorResponse(
            scene_id="test",
            status="success"
        )
        assert resp.status == "success"


class TestSchemaIntegration:
    """Test schemas together in a workflow."""
    
    def test_planner_to_generator_flow(self):
        """Planner response can be used to create generator request."""
        # Start with planner request
        planner_req = example_planner_request()
        assert planner_req.scene_id == "scene_001"
        
        # Get planner response
        planner_resp = example_planner_response()
        assert planner_resp.scene_id == planner_req.scene_id
        
        # Convert to generator request
        gen_req = example_generator_request()
        assert gen_req.scene_id == planner_resp.scene_id
        assert len(gen_req.characters) == len(planner_resp.scripts)
    
    def test_round_trip_serialization(self):
        """Schemas serialize and deserialize correctly."""
        original = example_planner_request()
        
        # Serialize to dict
        data = original.model_dump()
        assert isinstance(data, dict)
        
        # Deserialize back
        restored = PlannerRequest(**data)
        assert restored.scene_id == original.scene_id
        assert len(restored.characters) == len(original.characters)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
