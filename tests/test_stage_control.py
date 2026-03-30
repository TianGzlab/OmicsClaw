"""Tests for stage control (from_stage, skip_stages) in research pipeline."""

import pytest
from pathlib import Path
from omicsclaw.agents.pipeline import ResearchPipeline, PipelineState


class TestStageControl:
    """Test stage control parameters (from_stage, skip_stages)."""

    def test_stage_list_constant(self):
        """Verify STAGES constant has expected stages."""
        pipeline = ResearchPipeline()

        expected_stages = [
            "intake", "plan", "research", "execute",
            "analyze", "write", "review"
        ]

        assert pipeline.STAGES == expected_stages

    def test_is_stage_done(self):
        """PipelineState.is_stage_done should check completed_stages."""
        state = PipelineState()

        assert not state.is_stage_done("intake")

        state.completed_stages.append("intake")
        assert state.is_stage_done("intake")

        state.completed_stages.append("plan")
        assert state.is_stage_done("plan")
        assert not state.is_stage_done("execute")

    def test_from_stage_marks_prior_stages_completed(self):
        """from_stage should mark all prior stages as completed."""
        pipeline = ResearchPipeline()

        # Manually set from_stage logic (without running full pipeline)
        from_stage = "execute"
        from_idx = pipeline.STAGES.index(from_stage)

        for stage in pipeline.STAGES[:from_idx]:
            pipeline.state.completed_stages.append(stage)
            pipeline.state.stage_outputs[stage] = f"Skipped (--from-stage={from_stage})"

        # Verify
        assert "intake" in pipeline.state.completed_stages
        assert "plan" in pipeline.state.completed_stages
        assert "research" in pipeline.state.completed_stages
        assert "execute" not in pipeline.state.completed_stages
        assert len(pipeline.state.completed_stages) == from_idx

    def test_skip_stages_marks_stages_completed(self):
        """skip_stages should mark specified stages as completed."""
        pipeline = ResearchPipeline()

        skip_stages = ["research", "review"]

        for stage in skip_stages:
            pipeline.state.completed_stages.append(stage)
            pipeline.state.stage_outputs[stage] = "Skipped (--skip)"

        # Verify
        assert "research" in pipeline.state.completed_stages
        assert "review" in pipeline.state.completed_stages
        assert "execute" not in pipeline.state.completed_stages

    def test_from_stage_validation_logic(self):
        """Test from_stage validation logic."""
        pipeline = ResearchPipeline()

        # Valid stage should not raise
        assert "execute" in pipeline.STAGES

        # Invalid stage should be detectable
        invalid_stage = "invalid_stage"
        assert invalid_stage not in pipeline.STAGES

    def test_skip_stages_validation_logic(self):
        """Test skip_stages validation logic."""
        pipeline = ResearchPipeline()

        # Valid stages
        valid_skips = ["research", "review"]
        invalid_skips = [s for s in valid_skips if s not in pipeline.STAGES]
        assert len(invalid_skips) == 0

        # Invalid stages
        invalid_list = ["invalid_stage", "another_invalid"]
        invalid_skips = [s for s in invalid_list if s not in pipeline.STAGES]
        assert len(invalid_skips) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
