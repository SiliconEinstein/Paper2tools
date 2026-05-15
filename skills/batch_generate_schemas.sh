#!/bin/bash
# 批量为所有 Superconductivity workflow 生成 schema.json

WORKFLOWS_DIR="/personal/paper2tools_v2/data/Superconductivity/workflows_top50"
SCRIPT="/personal/paper2tools_v2/skills/generate_schema.py"
LOG_FILE="/personal/paper2tools_v2/data/Superconductivity/schema_generation.log"

# 清空日志
> "$LOG_FILE"

echo "=== 批量生成 Schema ==="
echo "工作流目录: $WORKFLOWS_DIR"
echo "日志文件: $LOG_FILE"
echo ""

# 统计总数
total=$(find "$WORKFLOWS_DIR" -maxdepth 1 -type d -name "cluster_*" | wc -l)
echo "发现 $total 个 cluster 目录"
echo ""

# 计数器
success=0
failed=0
skipped=0
current=0

# 遍历所有 cluster 目录
for cluster_dir in "$WORKFLOWS_DIR"/cluster_*; do
    current=$((current + 1))
    cluster_name=$(basename "$cluster_dir")

    echo "[$current/$total] 处理 $cluster_name ..."

    # 检查必需文件
    if [[ ! -f "$cluster_dir/paper_extractions.yaml" ]]; then
        echo "  ⚠ 跳过: 缺少 paper_extractions.yaml" | tee -a "$LOG_FILE"
        skipped=$((skipped + 1))
        continue
    fi

    if [[ ! -f "$cluster_dir/selected_chains.json" ]]; then
        echo "  ⚠ 跳过: 缺少 selected_chains.json" | tee -a "$LOG_FILE"
        skipped=$((skipped + 1))
        continue
    fi

    if [[ ! -f "$cluster_dir/workflow_structure.json" ]]; then
        echo "  ⚠ 跳过: 缺少 workflow_structure.json" | tee -a "$LOG_FILE"
        skipped=$((skipped + 1))
        continue
    fi

    # 检查是否已存在 schema.json
    if [[ -f "$cluster_dir/schema.json" ]]; then
        echo "  ⚠ 跳过: schema.json 已存在" | tee -a "$LOG_FILE"
        skipped=$((skipped + 1))
        continue
    fi

    # 运行生成脚本
    if python "$SCRIPT" "$cluster_dir" >> "$LOG_FILE" 2>&1; then
        echo "  ✓ 成功" | tee -a "$LOG_FILE"
        success=$((success + 1))
    else
        echo "  ✗ 失败 (详见日志)" | tee -a "$LOG_FILE"
        failed=$((failed + 1))
    fi

    echo ""
done

echo "=== 完成 ==="
echo "总计: $total"
echo "成功: $success"
echo "失败: $failed"
echo "跳过: $skipped"
echo ""
echo "详细日志: $LOG_FILE"
