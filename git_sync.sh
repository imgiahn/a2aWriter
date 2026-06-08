#!/bin/bash
cd /home/ec2-user/a2aWriter
git add -A
if ! git diff --cached --quiet; then
  git commit -m "auto: $(date +%Y-%m-%d) 발행기록"
fi
git push origin main >> /dev/null 2>&1 || true
