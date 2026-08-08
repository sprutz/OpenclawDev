# Confirmation-style dialogue examples

## Read-only status

**You:** What’s the status of OpenClaw?

**Agent:** Checking the gateway now.  
*(calls `openclaw_health` / `openclaw_get_status` target=`gateway`)*  
Gateway is healthy. Want the agent list or a full ops summary?

## List agents

**You:** Which agents are active?

**Agent:** Pulling the agent roster.  
*(calls `openclaw_list_agents`)*  
I see the default orchestrator and two named agents: ops and docs. Anything specific you want status on?

## Assign task with confirmation

**You:** Have OpenClaw draft a cutover checklist for the plant historian migration, high priority.

**Agent:** I will assign a high-priority task to the orchestrator: draft a cutover checklist for the plant historian migration. Should I proceed?

**You:** Yes, go ahead.

**Agent:** Assigning it now.  
*(calls `openclaw_assign_task` with `priority=high`, `confirmed=true`)*  
Assigned. OpenClaw acknowledged and started drafting the checklist.

## Rejected without confirmation

**You:** Pause the ops agent.

**Agent:** I can pause the ops agent. Confirm and I’ll do it.

**You:** Actually wait.

**Agent:** Standing by. No changes made.

## Urgent industrial escalation

**You:** Production SCADA sync looks stuck. Get me status and if needed assign urgent recovery.

**Agent:** Checking status first.  
*(calls `openclaw_get_status` target=`SCADA sync`)*  
Status shows the sync task idle with no recent progress. I can assign an urgent recovery task to the orchestrator. Confirm?

**You:** Confirm urgent recovery.

**Agent:** Assigning urgent recovery now.  
*(calls `openclaw_assign_task` priority=`urgent`, confirmed=`true`)*  
Urgent recovery task is in. I’ll keep this brief: OpenClaw accepted it.
