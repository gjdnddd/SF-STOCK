#!/bin/bash
# NextMove DB 일간 동기화 스크립트
# 역할: xlsx 신규 행 → BQ 업로드 → KRX 배치 채움
# 크론: 매일 KST 06:00 (UTC 21:00)

source /home/gjdnddd/.bashrc_env
cd /home/gjdnddd/SF-STOCK

LOGFILE="/home/gjdnddd/SF-STOCK/nextmove/sync.log"
TS="[$(date '+%Y-%m-%d %H:%M:%S')]"

echo "$TS === DB Sync Start ===" >> "$LOGFILE"

# 1. 최신 xlsx git pull
echo "$TS git pull..." >> "$LOGFILE"
git pull >> "$LOGFILE" 2>&1

# 2. 신규 행 BQ 업로드
echo "$TS local_sync..." >> "$LOGFILE"
python3 nextmove/local_sync.py >> "$LOGFILE" 2>&1

# 3. KRX 배치 (신규 행 + 미완 행 채움)
echo "$TS krx_batch..." >> "$LOGFILE"
python3 nextmove/step_krx_batch.py >> "$LOGFILE" 2>&1

echo "$TS === Done ===" >> "$LOGFILE"
echo "" >> "$LOGFILE"
