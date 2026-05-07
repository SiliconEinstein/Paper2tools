#!/usr/bin/env python3
"""
Generate decision tree visualization for qRT-PCR validation workflow.
"""

import json
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

# Load workflow structure
with open('data/bioinformatics/workflows/cluster_6/workflow_structure.json', 'r') as f:
    workflow = json.load(f)

# Create figure
fig, ax = plt.subplots(figsize=(14, 18))
ax.set_xlim(0, 10)
ax.set_ylim(0, 20)
ax.axis('off')

# Define colors
stage_color = '#E8F4F8'
decision_color = '#FFF4E6'
optional_color = '#F0F0F0'
edge_color = '#2C3E50'

# Stage positions (x, y, width, height)
stages = [
    {'id': 0, 'name': 'Input: High-throughput\nExpression Data', 'pos': (3, 18, 4, 1), 'color': '#D5E8D4'},
    {'id': 1, 'name': 'Stage 1: Gene Selection', 'pos': (3, 16, 4, 1.2), 'color': stage_color},
    {'id': 2, 'name': 'Stage 2: RNA Extraction\n& Reverse Transcription', 'pos': (3, 13.8, 4, 1.2), 'color': stage_color},
    {'id': 3, 'name': 'Stage 3: qRT-PCR\nExecution', 'pos': (3, 11.6, 4, 1.2), 'color': stage_color},
    {'id': 4, 'name': 'Stage 4: Normalization', 'pos': (3, 9.4, 4, 1.2), 'color': stage_color},
    {'id': 5, 'name': 'Stage 5: Quantification\n& Statistics', 'pos': (3, 7.2, 4, 1.2), 'color': stage_color},
    {'id': 6, 'name': 'Stage 6: Concordance\nAssessment', 'pos': (3, 5, 4, 1.2), 'color': stage_color},
    {'id': 7, 'name': 'Stage 7: Discrepancy\nInterpretation', 'pos': (3, 2.8, 4, 1.2), 'color': optional_color},
]

# Decision points
decisions = [
    {'stage': 1, 'text': 'Random vs Stratified\nvs Functional priority', 'pos': (7.5, 16.3)},
    {'stage': 2, 'text': 'Random hexamers vs\noligo(dT) vs gene-specific', 'pos': (7.5, 14.1)},
    {'stage': 3, 'text': 'SYBR Green (63.6%)\nvs TaqMan (31.8%)', 'pos': (7.5, 11.9)},
    {'stage': 4, 'text': 'Single vs Multi-HKG\ngeometric mean', 'pos': (7.5, 9.7)},
    {'stage': 5, 'text': 'Comparative Ct (45.5%)\nvs Standard curve (22.7%)', 'pos': (7.5, 7.5)},
    {'stage': 6, 'text': 'Concordance ≥90%?', 'pos': (7.5, 5.3)},
]

# Draw stages
for stage in stages:
    box = FancyBboxPatch(
        (stage['pos'][0], stage['pos'][1]),
        stage['pos'][2],
        stage['pos'][3],
        boxstyle='round,pad=0.1',
        facecolor=stage['color'],
        edgecolor=edge_color,
        linewidth=2
    )
    ax.add_patch(box)

    # Add text
    text_y = stage['pos'][1] + stage['pos'][3]/2
    ax.text(5, text_y, stage['name'],
            ha='center', va='center', fontsize=10, weight='bold')

    # Add coverage percentage for main stages
    if stage['id'] >= 1 and stage['id'] <= 6:
        ax.text(stage['pos'][0] + 0.2, stage['pos'][1] + 0.15,
                '100%', fontsize=8, color='#27AE60', weight='bold')
    elif stage['id'] == 7:
        ax.text(stage['pos'][0] + 0.2, stage['pos'][1] + 0.15,
                '68.2%', fontsize=8, color='#7F8C8D', weight='bold')

# Draw arrows between stages
for i in range(len(stages)-1):
    y_start = stages[i]['pos'][1]
    y_end = stages[i+1]['pos'][1] + stages[i+1]['pos'][3]

    if i == 5:  # Special arrow from stage 6 to optional stage 7
        arrow = FancyArrowPatch(
            (5, y_start), (5, y_end),
            arrowstyle='->,head_width=0.4,head_length=0.4',
            color='#7F8C8D',
            linewidth=1.5,
            linestyle='dashed'
        )
    else:
        arrow = FancyArrowPatch(
            (5, y_start), (5, y_end),
            arrowstyle='->,head_width=0.4,head_length=0.4',
            color=edge_color,
            linewidth=2
        )
    ax.add_patch(arrow)

# Draw decision boxes
for dec in decisions:
    box = FancyBboxPatch(
        (dec['pos'][0], dec['pos'][1] - 0.35),
        2.3, 0.7,
        boxstyle='round,pad=0.05',
        facecolor=decision_color,
        edgecolor='#E67E22',
        linewidth=1.5
    )
    ax.add_patch(box)
    ax.text(dec['pos'][0] + 1.15, dec['pos'][1], dec['text'],
            ha='center', va='center', fontsize=8, style='italic')

    # Draw connection line to stage
    stage_x = stages[dec['stage']]['pos'][0] + stages[dec['stage']]['pos'][2]
    stage_y = dec['pos'][1]
    ax.plot([stage_x, dec['pos'][0]], [stage_y, stage_y],
            color='#E67E22', linewidth=1, linestyle='dotted')

# Add conditional branch annotation
ax.text(5.5, 4, 'If <90%', fontsize=8, color='#7F8C8D', style='italic')
ax.text(5.5, 3.5, 'concordance', fontsize=8, color='#7F8C8D', style='italic')

# Add legend
legend_elements = [
    mpatches.Patch(facecolor=stage_color, edgecolor=edge_color, label='Main Stage (100% coverage)'),
    mpatches.Patch(facecolor=optional_color, edgecolor=edge_color, label='Optional Stage (68.2% coverage)'),
    mpatches.Patch(facecolor=decision_color, edgecolor='#E67E22', label='Decision Point'),
]
ax.legend(handles=legend_elements, loc='lower center', ncol=3, fontsize=9, frameon=True)

# Add title
ax.text(5, 19.5, 'qRT-PCR Validation Workflow Decision Tree',
        ha='center', va='center', fontsize=14, weight='bold')

# Add statistics box
stats_text = '''Key Statistics (n=22 papers):
• Median genes validated: 13
• Median concordance: 87.5%
• Range: 65-100%'''
ax.text(0.5, 1, stats_text, fontsize=8,
        bbox=dict(boxstyle='round', facecolor='#ECF0F1', alpha=0.8),
        verticalalignment='bottom')

plt.tight_layout()
plt.savefig('data/bioinformatics/workflows/cluster_6/decision_tree.png', dpi=300, bbox_inches='tight')
print('Decision tree saved to data/bioinformatics/workflows/cluster_6/decision_tree.png')
