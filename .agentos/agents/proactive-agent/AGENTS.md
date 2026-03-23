# proactive-agent

- id: proactive-agent
- name: Proactive Agent
- description: 自主执行定时任务和信息推送的 agent，可委派其他 agent 协作完成任务
- can_delegate_to: [email-agent, search-agent, data-analyst, doc-organizer]
- tools: [send_message, create_proactive_job, list_proactive_jobs, manage_proactive_job, fetch_url, read_file]
