import pytest

from omicsclaw.agents.pipeline import ResearchPipeline, PipelineState


class TestStageControl:
    def test_stage_list_constant(self):
        pipeline = ResearchPipeline()

        assert pipeline.STAGES == [
            "intake",
            "plan",
            "research",
            "execute",
            "analyze",
            "write",
            "review",
        ]

    def test_is_stage_done_uses_structured_store(self):
        state = PipelineState()

        assert not state.is_stage_done("intake")

        state.mark_stage_completed("intake")
        assert state.is_stage_done("intake")

        state.mark_stage_completed("plan")
        assert state.is_stage_done("plan")
        assert not state.is_stage_done("execute")

    def test_from_stage_marks_prior_stages_skipped(self):
        pipeline = ResearchPipeline()

        from_stage = "execute"
        from_idx = pipeline.STAGES.index(from_stage)

        for stage in pipeline.STAGES[:from_idx]:
            pipeline.state.mark_stage_skipped(
                stage,
                summary=f"Skipped (--from-stage={from_stage})",
            )

        assert pipeline.state.completed_stages == ["intake", "plan", "research"]
        assert pipeline.state.task_store.require("research").status == "skipped"
        assert "execute" not in pipeline.state.completed_stages

    def test_skip_stages_marks_stages_skipped(self):
        pipeline = ResearchPipeline()

        for stage in ["research", "review"]:
            pipeline.state.mark_stage_skipped(stage, summary="Skipped (--skip)")

        assert pipeline.state.completed_stages == ["research", "review"]
        assert pipeline.state.task_store.require("research").status == "skipped"
        assert pipeline.state.task_store.require("review").status == "skipped"
        assert "execute" not in pipeline.state.completed_stages

    def test_starting_new_stage_completes_previous_in_progress_stage(self):
        state = PipelineState()

        state.mark_stage_in_progress("plan", summary="creating plan")
        state.mark_stage_in_progress("research", summary="searching literature")

        assert state.task_store.require("plan").status == "completed"
        assert state.task_store.require("research").status == "in_progress"
        assert state.current_stage == "research"

    def test_from_stage_validation_logic(self):
        pipeline = ResearchPipeline()

        assert "execute" in pipeline.STAGES
        assert "invalid_stage" not in pipeline.STAGES

    def test_skip_stages_validation_logic(self):
        pipeline = ResearchPipeline()

        valid_skips = ["research", "review"]
        assert [s for s in valid_skips if s not in pipeline.STAGES] == []

        invalid_list = ["invalid_stage", "another_invalid"]
        assert len([s for s in invalid_list if s not in pipeline.STAGES]) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
