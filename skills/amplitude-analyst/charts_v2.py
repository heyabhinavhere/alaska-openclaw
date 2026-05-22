#!/usr/bin/env python3
"""
Alaska Chart Generator v2 — Designed for Slack readability
Clean, modern, mobile-first charts that look great in both dark and light mode.

Usage: python3 charts_v2.py <chart_type> <output_path> [args...]

Chart types:
  line    <output> <title> <labels_csv> <values_csv> [subtitle]
  bar     <output> <title> <labels_csv> <values_csv> [subtitle]
  funnel  <output> <title> <steps_csv> <values_csv> [subtitle]
  compare <output> <title> <labels_csv> <this_week_csv> <last_week_csv> [subtitle]
  distro  <output> <title> <labels_csv> <values_csv> [subtitle]

Design principles:
  - Mobile-first: 375px viewport on phone, charts must be legible
  - Story-first: Highlight peaks, current value, trends — not every data point
  - Slack-native: Works in dark AND light mode (semi-transparent dark bg)
  - Minimal: No chart junk, no unnecessary labels, clean typography
"""

import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.patheffects as pe
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

# ── Design System ──────────────────────────────────────────────
# Semi-dark background that works in both Slack modes
BG_COLOR = '#1a1d27'
CARD_BG = '#1a1d27'
TEXT_PRIMARY = '#f0f0f5'
TEXT_SECONDARY = '#8b8fa3'
TEXT_MUTED = '#5a5e72'
GRID_COLOR = '#2d3045'
BORDER_COLOR = '#2d3045'

# Accessible palette — visible on dark bg, not neon
BLUE = '#5B8DEF'        # Primary — data lines, bars
BLUE_LIGHT = '#7DA8F5'  # Hover/highlight state
BLUE_DIM = '#3A5A9E'    # De-emphasized
RED = '#EF6B6B'         # Negative/alert
GREEN = '#5BCC8A'       # Positive/success
AMBER = '#F0B95B'       # Warning
PURPLE = '#9B8FEF'      # Secondary data series
GRAY = '#4A4E63'        # Previous period / baseline

PALETTE = [BLUE, GREEN, AMBER, PURPLE, RED, '#EF8B5B']

# Typography
FONT_FAMILY = 'sans-serif'
plt.rcParams['font.family'] = FONT_FAMILY
plt.rcParams['font.size'] = 11


def _smart_x_labels(labels, max_labels=7):
    """Return indices to show for x-axis — never more than max_labels.
    Only shows labels at selected indices, blanks everything else."""
    n = len(labels)
    if n <= max_labels:
        return list(range(n)), labels
    
    # Always show first and last, evenly space the rest
    if max_labels <= 2:
        indices = [0, n - 1]
    else:
        # Evenly distribute between first and last
        inner_count = max_labels - 2
        step = (n - 1) / (inner_count + 1)
        indices = [0] + [int(round(step * (i + 1))) for i in range(inner_count)] + [n - 1]
        # Deduplicate while preserving order
        seen = set()
        deduped = []
        for idx in indices:
            if idx not in seen:
                seen.add(idx)
                deduped.append(idx)
        indices = deduped
    
    index_set = set(indices)
    shown_labels = [labels[i] if i in index_set else '' for i in range(n)]
    return indices, shown_labels


def _annotate_key_points(ax, x, values, color=BLUE):
    """Annotate only: current (last), peak, and trough — no label spam."""
    if not values:
        return
    
    n = len(values)
    peak_i = int(np.argmax(values))
    trough_i = int(np.argmin(values))
    last_i = n - 1
    
    annotated = set()
    
    # Helper to place annotation smartly
    def place(i, label, c, offset_y=16, bold=True):
        if i in annotated:
            return
        annotated.add(i)
        weight = 'bold' if bold else 'normal'
        txt = ax.annotate(
            label, (x[i], values[i]),
            textcoords='offset points', xytext=(0, offset_y),
            ha='center', fontsize=12, color=c, fontweight=weight,
            path_effects=[pe.withStroke(linewidth=3, foreground=BG_COLOR)]
        )
    
    # Current value — always shown, prominent
    place(last_i, str(int(values[last_i])), TEXT_PRIMARY, offset_y=16, bold=True)
    
    # Peak — if different from current
    if peak_i != last_i and abs(peak_i - last_i) > 1:
        place(peak_i, str(int(values[peak_i])), AMBER, offset_y=16)
    
    # Trough — only if significantly lower than peak and not too close to other annotations
    if (trough_i != last_i and trough_i != peak_i and 
        values[trough_i] < values[peak_i] * 0.4 and
        abs(trough_i - peak_i) > 2 and abs(trough_i - last_i) > 2):
        place(trough_i, str(int(values[trough_i])), TEXT_MUTED, offset_y=-20)


def _add_header(fig, title, subtitle=None, stats=None):
    """Add a clean header with title, subtitle, and optional stats."""
    y_title = 0.95
    fig.text(0.06, y_title, title, fontsize=16, fontweight='bold', 
             color=TEXT_PRIMARY, va='top', ha='left')
    
    sub_parts = []
    if subtitle:
        sub_parts.append(subtitle)
    
    # Add generation timestamp
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime('%b %d, %H:%M UTC')
    sub_parts.append(f'Generated {now}')
    
    if sub_parts:
        fig.text(0.06, y_title - 0.055, ' · '.join(sub_parts), fontsize=10, 
                 color=TEXT_SECONDARY, va='top', ha='left')
    
    if stats:
        # Right-aligned key stat
        fig.text(0.94, y_title, stats, fontsize=14, fontweight='bold',
                 color=GREEN if not stats.startswith('↓') else RED, 
                 va='top', ha='right')


def _compute_trend_text(values):
    """Compute a trend string comparing latest vs period start."""
    if len(values) < 2:
        return ''
    first_nonzero = next((v for v in values if v > 0), values[0])
    last = values[-1]
    if first_nonzero == 0:
        return ''
    pct = ((last - first_nonzero) / first_nonzero) * 100
    n = len(values)
    period = f'{n}d' if n <= 14 else f'{n}d'
    if pct > 0:
        return f'↑ {pct:.0f}% over {period}'
    elif pct < 0:
        return f'↓ {abs(pct):.0f}% over {period}'
    return '→ flat'


def _setup_figure(width=10, height=5, header_space=0.18):
    """Create figure with consistent styling and header space.
    Wider aspect ratio renders better on mobile Slack (image gets more horizontal pixels)."""
    fig = plt.figure(figsize=(width, height), facecolor=BG_COLOR)
    
    # Main chart area — leave room for header at top and labels at bottom
    ax = fig.add_axes([0.08, 0.12, 0.88, 0.68])
    ax.set_facecolor(BG_COLOR)
    
    # Minimal spines
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color(GRID_COLOR)
    ax.spines['bottom'].set_color(GRID_COLOR)
    ax.spines['left'].set_linewidth(0.5)
    ax.spines['bottom'].set_linewidth(0.5)
    
    # Grid — subtle horizontal only
    ax.grid(axis='y', color=GRID_COLOR, linestyle='-', alpha=0.3, linewidth=0.5)
    ax.grid(axis='x', visible=False)
    
    # Tick styling
    ax.tick_params(axis='both', colors=TEXT_MUTED, labelsize=10, length=0)
    ax.tick_params(axis='x', pad=8)
    ax.tick_params(axis='y', pad=4)
    
    # Y-axis: integers only
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True, nbins=5))
    
    return fig, ax


# ── Chart Types ─────────────────────────────────────────────────

def line_chart(output, title, labels, values, subtitle=None):
    fig, ax = _setup_figure()
    
    x = np.arange(len(labels))
    
    # Smart x-axis labels
    show_indices, shown_labels = _smart_x_labels(labels, max_labels=7)
    ax.set_xticks(x)
    ax.set_xticklabels(shown_labels, fontsize=10, color=TEXT_MUTED)
    
    # Gradient fill under the line
    ax.fill_between(x, values, alpha=0.08, color=BLUE)
    
    # Main line — smooth, no markers on every point
    ax.plot(x, values, color=BLUE, linewidth=2.5, solid_capstyle='round')
    
    # Subtle dots only at key points
    peak_i = int(np.argmax(values))
    last_i = len(values) - 1
    for i in [peak_i, last_i]:
        ax.plot(x[i], values[i], 'o', color=BLUE, markersize=7,
                markeredgecolor=BG_COLOR, markeredgewidth=2, zorder=5)
    
    # Annotate key points only
    _annotate_key_points(ax, x, values)
    
    # Y-axis padding
    ymin, ymax = min(values), max(values)
    padding = max((ymax - ymin) * 0.25, 2)
    ax.set_ylim(max(0, ymin - padding * 0.3), ymax + padding)
    
    # Header
    trend = _compute_trend_text(values)
    _add_header(fig, title, subtitle, trend)
    
    fig.savefig(output, dpi=180, bbox_inches='tight', facecolor=BG_COLOR, 
                pad_inches=0.3)
    plt.close()


def bar_chart(output, title, labels, values, subtitle=None):
    fig, ax = _setup_figure()
    
    x = np.arange(len(labels))
    n = len(labels)
    
    # Color bars — highlight max
    max_i = int(np.argmax(values))
    colors = [BLUE if i != max_i else BLUE_LIGHT for i in range(n)]
    
    bar_width = min(0.6, 8.0 / max(n, 1))
    bars = ax.bar(x, values, width=bar_width, color=colors, alpha=0.9, 
                  edgecolor='none', zorder=3)
    
    # Round the bar tops with a subtle effect
    for bar in bars:
        bar.set_linewidth(0)
    
    # Value labels — only on bars, clean integers
    for i, (bar, v) in enumerate(zip(bars, values)):
        color = TEXT_PRIMARY if i == max_i else TEXT_SECONDARY
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(values) * 0.03,
                str(int(v)), ha='center', va='bottom', fontsize=11, color=color,
                fontweight='bold' if i == max_i else 'normal')
    
    # Smart x-axis
    show_indices, shown_labels = _smart_x_labels(labels, max_labels=10)
    ax.set_xticks(x)
    ax.set_xticklabels(shown_labels, fontsize=10, color=TEXT_MUTED,
                       rotation=30 if n > 10 else 0,
                       ha='right' if n > 10 else 'center')
    
    # Y padding
    ax.set_ylim(0, max(values) * 1.2)
    
    # Header
    total = sum(values)
    _add_header(fig, title, subtitle, f'Total: {int(total)}')
    
    fig.savefig(output, dpi=180, bbox_inches='tight', facecolor=BG_COLOR,
                pad_inches=0.3)
    plt.close()


def funnel_chart(output, title, steps, values, subtitle=None):
    fig, ax = _setup_figure(width=10, height=max(5, len(steps) * 0.7 + 2))
    
    n = len(steps)
    y_pos = np.arange(n)
    max_val = max(values) if values else 1
    
    # Single-hue gradient: full blue at top → faded blue at bottom
    # Communicates funnel progression naturally
    colors = []
    for i in range(n):
        alpha = 0.9 - (i / max(n - 1, 1)) * 0.45  # 0.9 → 0.45
        r, g, b = 0.357, 0.553, 0.937  # BLUE rgb
        colors.append((r, g, b, alpha))
    
    bars = ax.barh(y_pos, values, color=colors, height=0.55, edgecolor='none', zorder=3)
    
    # Labels: step name on the left (outside bar), count+% on the right of bar
    for i, (bar, v, step) in enumerate(zip(bars, values, steps)):
        pct = f'{(v / values[0] * 100):.0f}%' if values[0] > 0 else '0%'
        
        # Step name — always left-aligned outside the bar area
        ax.text(-max_val * 0.02, i, step, ha='right', va='center',
                fontsize=10, color=TEXT_SECONDARY, fontweight='normal')
        
        # Count + percentage — inside bar if wide enough, outside if narrow
        label = f'{int(v)} ({pct})'
        if v > max_val * 0.3:
            ax.text(v - max_val * 0.015, i, label, ha='right', va='center',
                    fontsize=10, color='white', fontweight='bold',
                    path_effects=[pe.withStroke(linewidth=2, foreground=BG_COLOR)])
        else:
            ax.text(v + max_val * 0.015, i, label, ha='left', va='center',
                    fontsize=10, color=TEXT_SECONDARY, fontweight='bold')
    
    # Drop-off annotations between bars — only show significant drops
    biggest_drop_i = -1
    biggest_drop_val = 0
    for i in range(n - 1):
        if values[i] > 0:
            drop = ((values[i] - values[i + 1]) / values[i]) * 100
            if drop > biggest_drop_val:
                biggest_drop_val = drop
                biggest_drop_i = i
    
    for i in range(n - 1):
        if values[i] > 0:
            drop = ((values[i] - values[i + 1]) / values[i]) * 100
            if drop > 8:  # Only show meaningful drops
                color = RED if i == biggest_drop_i else TEXT_MUTED
                weight = 'bold' if i == biggest_drop_i else 'normal'
                ax.annotate(f'−{drop:.0f}%', xy=(max_val * 1.02, i + 0.5),
                           fontsize=9, color=color, fontweight=weight,
                           ha='left', va='center')
    
    ax.set_yticks([])
    # Leave space on left for step labels
    ax.set_xlim(-max_val * 0.01, max_val * 1.12)
    ax.invert_yaxis()
    ax.spines['left'].set_visible(False)
    
    # Adjust left margin to fit step labels
    fig.subplots_adjust(left=0.22)
    
    # Header
    conversion = f'{(values[-1] / values[0] * 100):.0f}%' if values[0] > 0 else '0%'
    _add_header(fig, title, subtitle, f'{conversion} end-to-end')
    
    fig.savefig(output, dpi=180, bbox_inches='tight', facecolor=BG_COLOR,
                pad_inches=0.3)
    plt.close()


def compare_chart(output, title, labels, this_week, last_week, subtitle=None):
    fig, ax = _setup_figure()
    
    x = np.arange(len(labels))
    width = 0.32
    
    # Previous period — muted
    ax.bar(x - width / 2, last_week, width, color=GRAY, alpha=0.5,
           edgecolor='none', label='Previous', zorder=3)
    
    # Current period — prominent
    bars = ax.bar(x + width / 2, this_week, width, color=BLUE, alpha=0.9,
                  edgecolor='none', label='Current', zorder=3)
    
    # Value labels on current bars only
    max_val = max(max(this_week), max(last_week))
    for bar, v in zip(bars, this_week):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max_val * 0.03,
                str(int(v)), ha='center', va='bottom', fontsize=10, 
                color=TEXT_PRIMARY, fontweight='bold')
    
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10, color=TEXT_MUTED)
    ax.set_ylim(0, max_val * 1.25)
    
    # Minimal legend
    leg = ax.legend(loc='upper right', frameon=True, facecolor=BG_COLOR,
                    edgecolor=GRID_COLOR, labelcolor=TEXT_SECONDARY, fontsize=9)
    leg.get_frame().set_alpha(0.8)
    
    # Header with WoW change
    this_total = sum(this_week)
    last_total = sum(last_week)
    if last_total > 0:
        pct = ((this_total - last_total) / last_total) * 100
        trend = f'↑ {pct:.0f}% WoW' if pct > 0 else f'↓ {abs(pct):.0f}% WoW'
    else:
        trend = ''
    _add_header(fig, title, subtitle, trend)
    
    fig.savefig(output, dpi=180, bbox_inches='tight', facecolor=BG_COLOR,
                pad_inches=0.3)
    plt.close()


def distro_chart(output, title, labels, values, subtitle=None):
    fig, ax = _setup_figure()
    
    x = np.arange(len(labels))
    n = len(labels)
    
    # Semantic gradient: low → high (red → amber → green) for ordinal data
    # Falls back to palette for non-ordinal
    GRADIENT_5 = [RED, AMBER, '#E8D44D', GREEN, '#3DAA6D']  # Poor → Excellent
    GRADIENT_GENERIC = [BLUE, GREEN, AMBER, PURPLE, RED, '#EF8B5B']
    
    # Use semantic gradient if 3-6 categories (likely ordinal), else palette
    if 3 <= n <= 6:
        # Interpolate gradient to match n
        grad = GRADIENT_5 if n <= 5 else GRADIENT_GENERIC
        colors = grad[:n]
    else:
        colors = [PALETTE[i % len(PALETTE)] for i in range(n)]
    
    bar_width = min(0.65, 7.0 / max(n, 1))
    
    bars = ax.bar(x, values, width=bar_width, color=colors, alpha=0.85,
                  edgecolor='none', zorder=3)
    
    total = sum(values)
    for bar, v in zip(bars, values):
        pct = f'{v / total * 100:.0f}%' if total > 0 else '0%'
        display = f'{int(v)} ({pct})' if total != 100 else f'{int(v)}%'
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(values) * 0.03,
                display, ha='center', va='bottom', fontsize=10, color=TEXT_SECONDARY,
                fontweight='bold')
    
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10, color=TEXT_MUTED,
                       rotation=30 if n > 6 else 0,
                       ha='right' if n > 6 else 'center')
    ax.set_ylim(0, max(values) * 1.25)
    
    _add_header(fig, title, subtitle, f'n={int(total)}')
    
    fig.savefig(output, dpi=180, bbox_inches='tight', facecolor=BG_COLOR,
                pad_inches=0.3)
    plt.close()


# ── CLI ─────────────────────────────────────────────────────────

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
        subtitle = sys.argv[6] if len(sys.argv) > 6 else None
        line_chart(output, title, labels, values, subtitle)
    
    elif chart_type == 'bar':
        labels = sys.argv[4].split(',')
        values = [float(x) for x in sys.argv[5].split(',')]
        subtitle = sys.argv[6] if len(sys.argv) > 6 else None
        bar_chart(output, title, labels, values, subtitle)
    
    elif chart_type == 'funnel':
        steps = sys.argv[4].split(',')
        values = [float(x) for x in sys.argv[5].split(',')]
        subtitle = sys.argv[6] if len(sys.argv) > 6 else None
        funnel_chart(output, title, steps, values, subtitle)
    
    elif chart_type == 'compare':
        labels = sys.argv[4].split(',')
        this_week = [float(x) for x in sys.argv[5].split(',')]
        last_week = [float(x) for x in sys.argv[6].split(',')]
        subtitle = sys.argv[7] if len(sys.argv) > 7 else None
        compare_chart(output, title, labels, this_week, last_week, subtitle)
    
    elif chart_type == 'distro':
        labels = sys.argv[4].split(',')
        values = [float(x) for x in sys.argv[5].split(',')]
        subtitle = sys.argv[6] if len(sys.argv) > 6 else None
        distro_chart(output, title, labels, values, subtitle)
    
    else:
        print(f'Unknown chart type: {chart_type}')
        sys.exit(1)
    
    print(f'Chart saved: {output}')
