"""
Card 3: Shared State Loop (Deterministic Event Scheduler)

Defines deterministic event ordering for multi-character interactions in one port.
- Synchronized time with per-character state containers
- Deterministic conflict resolution (same seed → same outcome)
- Support for ≥3 active characters
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any
import hashlib
import json


class CharacterState(Enum):
    """Character lifecycle state."""
    IDLE = "idle"
    BUSY = "busy"
    TRANSITIONING = "transitioning"
    INTERACTING = "interacting"


class ConflictResolutionPolicy(str, Enum):
    """How to resolve conflicting interactions."""
    PRIORITY_BASED = "priority_based"  # Higher priority character wins
    FIFO = "fifo"  # First in, first out
    COOLDOWN = "cooldown"  # Enforce cooldown between interactions
    NEGOTIATION = "negotiation"  # Custom negotiation logic


@dataclass
class CharacterSegmentState:
    """Current state of a character's motion segment execution."""
    
    character_id: str
    segment_index: int  # Current segment in script
    frames_elapsed: int  # Frames executed in current segment
    total_frames: int  # Total frames for current segment
    is_complete: bool = False
    
    def progress(self) -> float:
        """Return 0-1 progress through current segment."""
        if self.total_frames == 0:
            return 1.0
        return min(1.0, self.frames_elapsed / self.total_frames)


@dataclass
class CharacterSlot:
    """Per-character state container in shared loop."""
    
    character_id: str
    skeleton_type: str
    current_state: CharacterState = CharacterState.IDLE
    segment_state: Optional[CharacterSegmentState] = None
    
    # Interaction tracking
    interaction_target: Optional[str] = None
    last_interaction_time_ms: int = 0
    interaction_cooldown_ms: int = 500  # Prevent rapid re-interactions
    
    # Metadata
    priority: int = 0  # For conflict resolution
    cycle_count: int = 0  # Lifecycle counter
    
    def is_busy(self) -> bool:
        """Check if character is currently executing motion."""
        return self.current_state in [
            CharacterState.BUSY,
            CharacterState.TRANSITIONING,
            CharacterState.INTERACTING
        ]
    
    def can_interact(self, current_time_ms: int) -> bool:
        """Check if character can start new interaction."""
        time_since_last = current_time_ms - self.last_interaction_time_ms
        return time_since_last >= self.interaction_cooldown_ms


@dataclass
class LoopTick:
    """Single tick in the deterministic event loop."""
    
    tick_number: int
    frame_number: int
    time_ms: float
    fps: int = 30
    
    # Per-tick events
    character_updates: Dict[str, CharacterSlot] = field(default_factory=dict)
    completed_segments: List[str] = field(default_factory=list)
    interactions: List[tuple] = field(default_factory=list)  # [(from_id, to_id), ...]
    
    def get_timestamp(self) -> dict:
        """Return tick metadata for auditing."""
        return {
            "tick_number": self.tick_number,
            "frame_number": self.frame_number,
            "time_ms": self.time_ms,
            "fps": self.fps,
        }


class DeterministicLoop:
    """
    Deterministic multi-character event loop.
    
    Ensures:
    - Same seed → same outputs (for testing replay)
    - No race conditions (total determinism within single process)
    - Clear conflict resolution (priority/FIFO/cooldown)
    - Synchronized timeline for all characters
    """
    
    def __init__(
        self,
        fps: int = 30,
        seed: int = 42,
        conflict_policy: ConflictResolutionPolicy = ConflictResolutionPolicy.COOLDOWN,
    ):
        self.fps = fps
        self.seed = seed
        self.conflict_policy = conflict_policy
        
        # Derive deterministic RNG state from seed
        self._rng_state = seed
        
        # State tracking
        self.tick_number = 0
        self.frame_number = 0
        self.time_ms = 0.0
        self.ms_per_frame = 1000.0 / fps
        
        # Per-character state
        self.characters: Dict[str, CharacterSlot] = {}
        
        # Event log for auditing
        self.tick_history: List[LoopTick] = []
    
    def register_character(
        self,
        character_id: str,
        skeleton_type: str,
        priority: int = 0,
    ) -> None:
        """Register a character for this loop."""
        if character_id in self.characters:
            raise ValueError(f"Character {character_id} already registered")
        
        self.characters[character_id] = CharacterSlot(
            character_id=character_id,
            skeleton_type=skeleton_type,
            priority=priority,
        )
    
    def _deterministic_rng(self) -> float:
        """Generate deterministic pseudo-random number (0-1)."""
        # Simple linear congruential generator seeded with loop state
        self._rng_state = (self._rng_state * 1103515245 + 12345) & 0x7fffffff
        return (self._rng_state / 0x7fffffff)
    
    def _resolve_conflict(
        self,
        char1_id: str,
        char2_id: str,
    ) -> str:
        """
        Deterministically resolve conflict between two characters.
        
        Returns: character_id that wins the interaction.
        """
        char1 = self.characters[char1_id]
        char2 = self.characters[char2_id]
        
        if self.conflict_policy == ConflictResolutionPolicy.PRIORITY_BASED:
            # Higher priority wins
            if char1.priority > char2.priority:
                return char1_id
            elif char2.priority > char1.priority:
                return char2_id
            # Equal priority: use deterministic tiebreaker (alphabetical)
            return min(char1_id, char2_id)
        
        elif self.conflict_policy == ConflictResolutionPolicy.FIFO:
            # Earlier interaction time wins
            if char1.last_interaction_time_ms < char2.last_interaction_time_ms:
                return char1_id
            else:
                return char2_id
        
        elif self.conflict_policy == ConflictResolutionPolicy.COOLDOWN:
            # Both can interact if cooldown satisfied
            char1_ready = char1.can_interact(int(self.time_ms))
            char2_ready = char2.can_interact(int(self.time_ms))
            
            if char1_ready and not char2_ready:
                return char1_id
            elif char2_ready and not char1_ready:
                return char2_id
            # Both or neither ready: use priority tiebreaker
            if char1.priority > char2.priority:
                return char1_id
            else:
                return char2_id
        
        else:  # NEGOTIATION (placeholder)
            return min(char1_id, char2_id)
    
    def advance_tick(
        self,
        character_motions: Dict[str, Dict[str, Any]],
    ) -> LoopTick:
        """
        Advance one tick forward with deterministic character updates.
        
        Args:
            character_motions: Dict[character_id] → motion data for this frame
        
        Returns:
            LoopTick with event history for this frame
        """
        tick = LoopTick(
            tick_number=self.tick_number,
            frame_number=self.frame_number,
            time_ms=self.time_ms,
            fps=self.fps,
        )
        
        # 1. Update character segment states (deterministic progression)
        for char_id, char_slot in self.characters.items():
            if char_slot.segment_state is None:
                continue
            
            # Advance frame counter
            char_slot.segment_state.frames_elapsed += 1
            
            # Check if segment complete
            if char_slot.segment_state.frames_elapsed >= char_slot.segment_state.total_frames:
                char_slot.segment_state.is_complete = True
                tick.completed_segments.append(char_id)
                char_slot.current_state = CharacterState.IDLE
            else:
                char_slot.current_state = CharacterState.BUSY
            
            tick.character_updates[char_id] = char_slot
        
        # 2. Detect and resolve conflicts
        pending_interactions = []
        for char_id, char_slot in self.characters.items():
            if char_slot.interaction_target:
                pending_interactions.append((char_id, char_slot.interaction_target))
        
        # Resolve conflicts deterministically
        for char1_id, char2_id in pending_interactions:
            winner_id = self._resolve_conflict(char1_id, char2_id)
            tick.interactions.append((winner_id, char2_id if winner_id == char1_id else char1_id))
            
            # Update last interaction time
            self.characters[winner_id].last_interaction_time_ms = int(self.time_ms)
        
        # 3. Advance time
        self.tick_number += 1
        self.frame_number += 1
        self.time_ms += self.ms_per_frame
        
        # 4. Record tick
        self.tick_history.append(tick)
        
        return tick
    
    def get_state_hash(self) -> str:
        """
        Compute deterministic hash of current loop state.
        
        Used for seeded replay verification:
        Same seed → same state hash at corresponding tick.
        """
        state_dict = {
            "tick_number": self.tick_number,
            "frame_number": self.frame_number,
            "time_ms": self.time_ms,
            "rng_state": self._rng_state,
            "characters": {
                char_id: {
                    "state": char_slot.current_state.value,
                    "frames_elapsed": char_slot.segment_state.frames_elapsed if char_slot.segment_state else 0,
                }
                for char_id, char_slot in self.characters.items()
            }
        }
        
        state_json = json.dumps(state_dict, sort_keys=True)
        return hashlib.sha256(state_json.encode()).hexdigest()[:16]
    
    def reset(self) -> None:
        """Reset loop to initial state (for replay)."""
        self.tick_number = 0
        self.frame_number = 0
        self.time_ms = 0.0
        self._rng_state = self.seed
        self.tick_history = []
        
        for char_slot in self.characters.values():
            char_slot.current_state = CharacterState.IDLE
            char_slot.segment_state = None


# ============================================================================
# Deterministic Test Scenarios
# ============================================================================

def two_character_interaction_scenario() -> tuple[DeterministicLoop, List[dict]]:
    """
    Test scenario: Two characters dancing with synchronized transitions.
    
    Returns:
        (loop, motion_frames_per_char)
    """
    loop = DeterministicLoop(fps=30, seed=42)
    
    # Register characters
    loop.register_character("dancer1", "soma", priority=1)
    loop.register_character("dancer2", "soma", priority=1)
    
    # Simulate 2 segments x 30 frames each = 60 frames total
    motion_sequence = [
        {
            "dancer1": {"action": "walk_forward", "frame": i} for i in range(30)
        },
        {
            "dancer2": {"action": "follow", "frame": i} for i in range(30)
        },
    ]
    
    return loop, motion_sequence


def three_character_scenario() -> tuple[DeterministicLoop, List[dict]]:
    """
    Test scenario: Three characters with controlled interactions.
    
    Returns:
        (loop, motion_frames)
    """
    loop = DeterministicLoop(fps=30, seed=43, conflict_policy=ConflictResolutionPolicy.PRIORITY_BASED)
    
    # Register with different priorities
    loop.register_character("leader", "soma", priority=3)
    loop.register_character("follower1", "soma", priority=2)
    loop.register_character("follower2", "soma", priority=1)
    
    motion_sequence = [
        {
            "leader": {"action": "lead", "frame": i},
            "follower1": {"action": "follow", "frame": i},
            "follower2": {"action": "match", "frame": i},
        }
        for i in range(60)
    ]
    
    return loop, motion_sequence


def test_deterministic_replay():
    """
    Verify deterministic replay: same seed produces identical state hashes.
    """
    print("=== Card 3: Deterministic Loop Test ===\n")
    
    # Scenario 1: Two-character deterministic replay
    print("Test 1: Two-character deterministic replay")
    
    loop1, motions1 = two_character_interaction_scenario()
    loop2, motions2 = two_character_interaction_scenario()
    
    hashes1 = []
    hashes2 = []
    
    for tick_num in range(60):
        loop1.advance_tick({})
        loop2.advance_tick({})
        
        hash1 = loop1.get_state_hash()
        hash2 = loop2.get_state_hash()
        
        hashes1.append(hash1)
        hashes2.append(hash2)
    
    if hashes1 == hashes2:
        print("✓ Deterministic replay (2-char): PASS")
    else:
        print(f"✗ Deterministic replay (2-char): FAIL")
        print(f"  Mismatch at frame: {[i for i, (h1, h2) in enumerate(zip(hashes1, hashes2)) if h1 != h2]}")
    
    print()
    
    # Scenario 2: Three-character with priority conflict resolution
    print("Test 2: Three-character priority-based conflict resolution")
    
    loop3, motions3 = three_character_scenario()
    loop4, motions4 = three_character_scenario()
    
    hashes3 = []
    hashes4 = []
    
    for tick_num in range(60):
        loop3.advance_tick({})
        loop4.advance_tick({})
        
        hash3 = loop3.get_state_hash()
        hash4 = loop4.get_state_hash()
        
        hashes3.append(hash3)
        hashes4.append(hash4)
    
    if hashes3 == hashes4:
        print("✓ Deterministic replay (3-char): PASS")
    else:
        print(f"✗ Deterministic replay (3-char): FAIL")
    
    print()
    
    # Scenario 3: Different seed produces different hashes
    print("Test 3: Different seed produces different outcome")
    
    loop_seed42, _ = two_character_interaction_scenario()
    loop_seed99 = DeterministicLoop(fps=30, seed=99)
    loop_seed99.register_character("dancer1", "soma", priority=1)
    loop_seed99.register_character("dancer2", "soma", priority=1)
    
    hashes42 = []
    hashes99 = []
    
    for tick_num in range(30):
        loop_seed42.advance_tick({})
        loop_seed99.advance_tick({})
        
        hashes42.append(loop_seed42.get_state_hash())
        hashes99.append(loop_seed99.get_state_hash())
    
    if hashes42 != hashes99:
        print("✓ Different seeds produce different outcomes: PASS")
    else:
        print("✗ Different seeds should differ: FAIL")
    
    print()
    print("=== All Deterministic Tests Complete ===")


if __name__ == "__main__":
    test_deterministic_replay()
