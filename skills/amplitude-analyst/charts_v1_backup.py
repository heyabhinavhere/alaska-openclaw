#!/usr/bin/env python3
"""
Alaska Chart Generator — Amplitude metrics → PNG charts → Slack upload
Usage: python3 charts.py <chart_type> <output_path> [args...]

Chart types:
  line    <output> <title> <labels_csv> <values_csv> [color]
  bar     <output> <title> <labels_csv> <values_csv> [color]
  funnel  <output> <title> <steps_csv> <values_csv>
  compare <output> <title> <labels_csv> <this_week_csv> <last_week_csv>
  distro  <output> <title> <labels_csv> <values_csv>

Examples:
  python3 charts.py line /tmp/dau.png "DAU — Apr 21-27" "Apr 21,Apr 22,Apr 23,Apr 24,Apr 25,Apr 26,Apr 27" "7,9,12,11,8,5,6"
  python3 charts.py bar /tmp/events.png "Top Events" "chat,credit_report,card_link" "120,85,14"
  python3 charts.py funnel /tmp/funnel.png "Signup Funnel" "Sign Up,OTP,Spin Wheel,Card Link" "90,63,34,3"
  python3 charts.py compare /tmp/wow.png "DAU WoW" "Mon,Tue,Wed,Thu,Fri,Sat,Sun" "7,9,12,11,8,5,6" "10,11,9,12,10,7,8"
  python3 charts.py distro /tmp/credit.png "Credit Score Distribution" "Below 580,580-669,670-739,740-799,800+" "32,39,18,8,3"
"""

import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

# BON Credit brand-ish dark theme
BG_COLOR = '#0f1117'
TEXT_COLOR = '#e0e0e0'
GRID_COLOR = '#2a2a3a'
PRIMARY = '#00d4ff'
SECONDARY = '#ff6b6b'
ACCENT = '#ffd93d'
PALETTE = ['#00d4ff', '#ff6b6b', '#ffd93d', '#6bcb77', '#a78bfa', '#f472b6']

def setup_ax(fig, ax, title):
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)
    ax.set_title(title, fontsize=14, color=TEXT_COLOR, fontweight='bold', pad=15)
    ax.tick_params(colors='#888888', labelsize=10)
    for spine in ax.spines.values():
        spine.set_color(GRID_COLOR)
    ax.grid(axis='y', color=GRID_COLOR, linestyle='--', alpha=0.5)

def line_chart(output, title, labels, values, color=PRIMARY):
    fig, ax = plt.subplots(figsize=(8, 4))
    setup_ax(fig, ax, title)
    
    x = range(len(labels))
    ax.plot(x, values, color=color, linewidth=2.5, marker='o', markersize=8, 
            markerfacecolor=color, markeredgecolor='white', markeredgewidth=1.5)
    ax.fill_between(x, values, alpha=0.12, color=color)
    
    for i, v in enumerate(values):
        ax.annotate(str(v), (i, v), textcoords='offset points', xytext=(0, 12),
                    ha='center', fontsize=11, color='white', fontweight='bold')
    
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=0)
    ax.set_ylabel('', fontsize=11, color='#888888')
    
    plt.tight_layout()
    plt.savefig(output, dpi=150, bbox_inches='tight', facecolor=BG_COLOR)
    plt.close()

def bar_chart(output, title, labels, values, color=PRIMARY):
    fig, ax = plt.subplots(figsize=(8, 4))
    setup_ax(fig, ax, title)
    
    x = range(len(labels))
    bars = ax.bar(x, values, color=color, alpha=0.85, edgecolor='none', width=0.6)
    
    for bar, v in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(values)*0.02,
                str(v), ha='center', va='bottom', fontsize=11, color='white', fontweight='bold')
    
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=0 if len(labels) <= 7 else 30, ha='right' if len(labels) > 7 else 'center')
    
    plt.tight_layout()
    plt.savefig(output, dpi=150, bbox_inches='tight', facecolor=BG_COLOR)
    plt.close()

def funnel_chart(output, title, steps, values):
    fig, ax = plt.subplots(figsize=(8, 5))
    setup_ax(fig, ax, title)
    
    y_pos = range(len(steps) - 1, -1, -1)
    max_val = max(values)
    colors = [PALETTE[i % len(PALETTE)] for i in range(len(steps))]
    
    bars = ax.barh(y_pos, values, color=colors, alpha=0.85, height=0.6, edgecolor='none')
    
    for i, (bar, v, step) in enumerate(zip(bars, values, steps)):
        pct = f'{(v/values[0]*100):.0f}%' if values[0] > 0 else '0%'
        label = f'{step}: {v} ({pct})'
        ax.text(max_val * 0.02, bar.get_y() + bar.get_height()/2, label,
                va='center', fontsize=11, color='white', fontweight='bold')
    
    # Drop-off annotations
    for i in range(len(values) - 1):
        if values[i] > 0:
            drop = ((values[i] - values[i+1]) / values[i]) * 100
            ax.annotate(f'↓ {drop:.0f}%', xy=(values[i+1], len(steps)-2-i),
                       textcoords='offset points', xytext=(10, 0),
                       fontsize=9, color=SECONDARY, fontweight='bold')
    
    ax.set_yticks([])
    ax.set_xlabel('')
    ax.invert_yaxis()
    
    plt.tight_layout()
    plt.savefig(output, dpi=150, bbox_inches='tight', facecolor=BG_COLOR)
    plt.close()

def compare_chart(output, title, labels, this_week, last_week):
    fig, ax = plt.subplots(figsize=(8, 4))
    setup_ax(fig, ax, title)
    
    x = np.arange(len(labels))
    width = 0.35
    
    bars1 = ax.bar(x - width/2, last_week, width, label='Last Week', color='#555577', alpha=0.7)
    bars2 = ax.bar(x + width/2, this_week, width, label='This Week', color=PRIMARY, alpha=0.85)
    
    for bar, v in zip(bars2, this_week):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(max(this_week), max(last_week))*0.02,
                str(v), ha='center', va='bottom', fontsize=10, color=PRIMARY, fontweight='bold')
    
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend(facecolor=BG_COLOR, edgecolor=GRID_COLOR, labelcolor=TEXT_COLOR)
    
    plt.tight_layout()
    plt.savefig(output, dpi=150, bbox_inches='tight', facecolor=BG_COLOR)
    plt.close()

def distro_chart(output, title, labels, values):
    fig, ax = plt.subplots(figsize=(8, 4))
    setup_ax(fig, ax, title)
    
    colors = [PALETTE[i % len(PALETTE)] for i in range(len(labels))]
    bars = ax.bar(range(len(labels)), values, color=colors, alpha=0.85, edgecolor='none', width=0.6)
    
    total = sum(values)
    for bar, v in zip(bars, values):
        pct = f'{v}%' if total == 100 else f'{v} ({v/total*100:.0f}%)'
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(values)*0.02,
                pct, ha='center', va='bottom', fontsize=10, color='white', fontweight='bold')
    
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=0 if len(labels) <= 6 else 30, ha='right' if len(labels) > 6 else 'center')
    
    plt.tight_layout()
    plt.savefig(output, dpi=150, bbox_inches='tight', facecolor=BG_COLOR)
    plt.close()

if __name__ == '__main__':
    if len(sys.argv) < 5:
        print(__doc__)
        sys.exit(1)
    
    chart_type = sys.argv[1]
    output = sys.argv[2]
    title = sys.argv[3]
    
    if chart_type == 'line':
        labels = sys.argv[4].split(',')
        values = [float(x) for x in sys.argv[5].split(',')]
        color = sys.argv[6] if len(sys.argv) > 6 else PRIMARY
        line_chart(output, title, labels, values, color)
    
    elif chart_type == 'bar':
        labels = sys.argv[4].split(',')
        values = [float(x) for x in sys.argv[5].split(',')]
        color = sys.argv[6] if len(sys.argv) > 6 else PRIMARY
        bar_chart(output, title, labels, values, color)
    
    elif chart_type == 'funnel':
        steps = sys.argv[4].split(',')
        values = [float(x) for x in sys.argv[5].split(',')]
        funnel_chart(output, title, steps, values)
    
    elif chart_type == 'compare':
        labels = sys.argv[4].split(',')
        this_week = [float(x) for x in sys.argv[5].split(',')]
        last_week = [float(x) for x in sys.argv[6].split(',')]
        compare_chart(output, title, labels, this_week, last_week)
    
    elif chart_type == 'distro':
        labels = sys.argv[4].split(',')
        values = [float(x) for x in sys.argv[5].split(',')]
        distro_chart(output, title, labels, values)
    
    else:
        print(f'Unknown chart type: {chart_type}')
        sys.exit(1)
    
    print(f'Chart saved: {output}')
