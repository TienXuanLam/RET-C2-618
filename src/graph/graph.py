"""AgentCore Platform v1.0"""

# Cat 2 — Multi-step domain workflow (job-to-be-done)
# SOP -> compliance quiz generation. The proposal's 3-step pipeline
# (PreProcess -> Main/ToolCallingAgent -> Output) maps directly onto
# AgentBaseGraph's 3 fixed domain slots — see docs/02_design.md
# "Node mapping note" for the rationale (no GraphNode subgraph needed).

from framework.graph.agent_base_graph import AgentBaseGraph

from src.nodes.pre_process_node import PreProcessNode
from src.nodes.main_node import MainNode
from src.nodes.post_process_node import PostProcessNode
from src.schemas.state import State


class RetailStaffSOPQuizGeneratorAgent(AgentBaseGraph):
    """Generates a compliance-tagged quiz from a retail SOP document."""

    @property
    def name(self) -> str:
        return "RetailStaffSOPQuizGeneratorAgent"

    @property
    def state_schema(self) -> type:
        return State

    def register_nodes(self) -> None:
        super().register_nodes()  # injects InitializeNode + FinalizeNode

        llm = self.config["llm"]
        self._nodes["pre_process"] = PreProcessNode()
        self._nodes["main"] = MainNode(llm)
        self._nodes["post_process"] = PostProcessNode()
