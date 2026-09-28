from fastapi import APIRouter
from app.agent.schemas import ComplaintWorkflowRequest, ComplaintWorkflowResponse
from app.workflows.complaint_workflow import complaint_workflow

router = APIRouter(prefix="/api/workflows", tags=["workflows"])

@router.post("/complaint", response_model=ComplaintWorkflowResponse)
def trigger_complaint_workflow(req: ComplaintWorkflowRequest):
    return complaint_workflow.run(req)
