"""Generate independent, authored fixtures in Markdown, Word, and PDF."""
from pathlib import Path
from docx import Document
root=Path('data/domains/demo/raw'); root.mkdir(parents=True,exist_ok=True)
topics=[('backup','Backup retention is 30 days. A full backup runs every Sunday at 02:00. Restore requests require a ticket.'),
('network','Network incidents must include the source address and destination port. Engineers inspect routing tables before changing firewall rules.'),
('account','New accounts require manager approval. Temporary access expires after seven days. Shared accounts are prohibited.'),
('storage','Storage alerts trigger at 80 percent usage. Archive files older than 180 days after the owner approves retention.'),
('release','Release changes require a staging test. Rollback begins if error rate exceeds five percent within ten minutes.'),
('database','Database maintenance occurs Saturday at 01:00. Validate backups and replication lag before upgrading the database.'),
('incident','Critical incidents require an on-call response within fifteen minutes. Record a timeline and prepare a postmortem.'),
('security','Security keys rotate every 90 days. Never store access tokens in source code. Audit privileged access monthly.'),
('monitor','Monitoring samples service latency every minute. Alert after three consecutive failures and notify the service owner.'),
('onboarding','New engineers complete onboarding within five working days. The training covers code review and incident handling.')]
for i in range(60):
    topic,text=topics[i%len(topics)]
    # Unique service-specific facts keep fixtures disjoint, while related policies produce hard negatives.
    title=f'Service {i:02d} {topic} policy'
    content=f'{title}\nService identifier S{i:02d}. The assigned team is Team{i:02d}. The escalation code is E{1000+i}. {text}'
    if i%3==0:
        doc=Document();doc.add_heading(title,0);doc.add_paragraph(content);doc.save(root/f'{i:02d}.docx')
    elif i%3==1:
        (root/f'{i:02d}.md').write_text('# '+content,encoding='utf-8')
    else:
        # LibreOffice writes PDF inside the container; no PDF generation dependency on the host.
        import subprocess,tempfile
        with tempfile.TemporaryDirectory() as tmp:
            doc=Document();doc.add_heading(title,0);doc.add_paragraph(content);p=Path(tmp)/f'{i:02d}.docx';doc.save(p)
            subprocess.run(['libreoffice','-env:UserInstallation=file://'+tmp+'/profile','--headless','--convert-to','pdf','--outdir',str(root.resolve()),str(p)],check=True,capture_output=True)
print(f'Created 60 documents in {root}')
