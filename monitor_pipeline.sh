#!/bin/bash
# 监控脚本 - 每5分钟检查一次流水线状态，遇到错误自动处理

LOG_FILE="logs/full_pipeline.log"
PID_FILE="logs/pipeline.pid"
MONITOR_LOG="logs/monitor.log"
CHECK_INTERVAL=300  # 5分钟

log_monitor() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$MONITOR_LOG"
}

check_status() {
    if [ ! -f "$PID_FILE" ]; then
        log_monitor "PID file not found, pipeline may have completed"
        return 1
    fi

    PID=$(cat "$PID_FILE")

    if ! ps -p "$PID" > /dev/null 2>&1; then
        log_monitor "Pipeline process $PID not running"

        # 检查是否正常完成
        if tail -20 "$LOG_FILE" | grep -q "Pipeline Completed"; then
            log_monitor "✓ Pipeline completed successfully"
            return 1
        else
            log_monitor "✗ Pipeline terminated unexpectedly"
            tail -50 "$LOG_FILE" >> "$MONITOR_LOG"
            return 1
        fi
    fi

    # 进程运行中，打印最新状态
    log_monitor "Pipeline running (PID: $PID)"

    # 提取最新进度
    LAST_LINES=$(tail -10 "$LOG_FILE")

    # Step1 进度
    STEP1_JOURNAL=$(echo "$LAST_LINES" | grep "\[Journal_Test\].*Step1" | tail -1)
    STEP1_RANDOM=$(echo "$LAST_LINES" | grep "\[Random50k_Test\].*Step1" | tail -1)

    # Step2 进度
    STEP2_JOURNAL=$(echo "$LAST_LINES" | grep "\[Journal_Test\].*Step2" | tail -1)
    STEP2_RANDOM=$(echo "$LAST_LINES" | grep "\[Random50k_Test\].*Step2" | tail -1)

    # Step3 进度
    STEP3_JOURNAL=$(echo "$LAST_LINES" | grep "\[Journal_Test\].*Step3" | tail -1)
    STEP3_RANDOM=$(echo "$LAST_LINES" | grep "\[Random50k_Test\].*Step3" | tail -1)

    # 打印进度
    [ -n "$STEP1_JOURNAL" ] && log_monitor "  Journal: $STEP1_JOURNAL"
    [ -n "$STEP1_RANDOM" ] && log_monitor "  Random50k: $STEP1_RANDOM"
    [ -n "$STEP2_JOURNAL" ] && log_monitor "  Journal: $STEP2_JOURNAL"
    [ -n "$STEP2_RANDOM" ] && log_monitor "  Random50k: $STEP2_RANDOM"
    [ -n "$STEP3_JOURNAL" ] && log_monitor "  Journal: $STEP3_JOURNAL"
    [ -n "$STEP3_RANDOM" ] && log_monitor "  Random50k: $STEP3_RANDOM"

    # 检查错误
    RECENT_ERRORS=$(tail -50 "$LOG_FILE" | grep -i "error\|exception\|failed" | tail -3)
    if [ -n "$RECENT_ERRORS" ]; then
        log_monitor "  ⚠ Recent errors detected:"
        echo "$RECENT_ERRORS" | while read line; do
            log_monitor "    $line"
        done
    fi

    # 检查是否卡住（10分钟无输出）
    LAST_MOD=$(stat -c %Y "$LOG_FILE" 2>/dev/null || echo 0)
    NOW=$(date +%s)
    IDLE_TIME=$((NOW - LAST_MOD))

    if [ $IDLE_TIME -gt 600 ]; then
        log_monitor "  ⚠ WARNING: No output for $IDLE_TIME seconds"
    fi

    return 0
}

log_monitor "========== Monitor Started =========="
log_monitor "Checking every $CHECK_INTERVAL seconds"

while true; do
    check_status
    if [ $? -ne 0 ]; then
        log_monitor "========== Monitor Exiting =========="
        exit 0
    fi
    sleep $CHECK_INTERVAL
done
