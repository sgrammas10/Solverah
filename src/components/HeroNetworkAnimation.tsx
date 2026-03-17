import React, { useEffect, useRef } from 'react';

// ── Precomputed constants ─────────────────────────────────────────────────────

const NODES = [
  { id: 'A', cx: 82,  cy: 310 },
  { id: 'B', cx: 185, cy: 148 },
  { id: 'C', cx: 148, cy: 245 },
  { id: 'D', cx: 295, cy: 92  },
  { id: 'E', cx: 255, cy: 195 },
  { id: 'F', cx: 188, cy: 368 },
  { id: 'G', cx: 365, cy: 168 },
  { id: 'H', cx: 340, cy: 295 },
  { id: 'I', cx: 430, cy: 88  },
  { id: 'J', cx: 468, cy: 205 },
  { id: 'K', cx: 415, cy: 325 },
  { id: 'L', cx: 552, cy: 128 },
  { id: 'M', cx: 538, cy: 248 },
  { id: 'N', cx: 575, cy: 355 },
  { id: 'O', cx: 648, cy: 175 },
  { id: 'P', cx: 662, cy: 295 },
  { id: 'Q', cx: 728, cy: 112 },
  { id: 'R', cx: 745, cy: 228 },
  { id: 'S', cx: 318, cy: 398 },
  { id: 'T', cx: 508, cy: 412 },
] as const;

type NodeId = typeof NODES[number]['id'];

const NODE_MAP: Record<string, { cx: number; cy: number }> = {};
NODES.forEach(n => { NODE_MAP[n.id] = { cx: n.cx, cy: n.cy }; });

function makePath(a: string, b: string, curveOffset: number) {
  const { cx: x1, cy: y1 } = NODE_MAP[a];
  const { cx: x2, cy: y2 } = NODE_MAP[b];
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.hypot(dx, dy) || 1;
  const px = (-dy / len) * curveOffset;
  const py = (dx / len) * curveOffset;
  const cpx = (mx + px).toFixed(1);
  const cpy = (my + py).toFixed(1);
  return {
    d: `M ${x1} ${y1} C ${cpx} ${cpy} ${cpx} ${cpy} ${x2} ${y2}`,
    approxLength: len * 1.25,
  };
}

// [from, to, curveOffset, colorType]
const EDGE_DEFS: [string, string, number, 'sage' | 'tan'][] = [
  ['A', 'C',  40, 'sage'], ['A', 'F',  35, 'tan' ],
  ['C', 'B', -45, 'tan' ], ['C', 'E',  38, 'sage'],
  ['B', 'D',  50, 'tan' ], ['B', 'E', -30, 'sage'],
  ['D', 'G', -42, 'sage'], ['D', 'I',  55, 'tan' ],
  ['E', 'G',  35, 'tan' ], ['E', 'H', -40, 'sage'],
  ['F', 'H',  60, 'tan' ], ['F', 'S',  35, 'sage'],
  ['G', 'J', -38, 'tan' ], ['G', 'I', -50, 'sage'],
  ['H', 'K',  40, 'tan' ], ['H', 'S', -55, 'sage'],
  ['I', 'L', -45, 'tan' ], ['J', 'L',  50, 'sage'],
  ['J', 'M', -35, 'tan' ], ['K', 'N',  45, 'sage'],
  ['K', 'T', -60, 'tan' ], ['L', 'O', -40, 'sage'],
  ['M', 'N',  55, 'tan' ], ['M', 'R', -45, 'sage'],
  ['N', 'T',  38, 'tan' ], ['O', 'Q', -50, 'sage'],
  ['O', 'R',  35, 'tan' ], ['P', 'R', -40, 'sage'],
  ['P', 'N',  48, 'tan' ], ['Q', 'R', -55, 'sage'],
  ['S', 'T',  40, 'tan' ],
  // Extra edges required by animation sequences
  ['L', 'Q', -35, 'tan' ], ['L', 'M',  50, 'sage'],
  ['K', 'S', -45, 'tan' ],
];

type EdgeData = {
  id: string;
  from: string;
  to: string;
  d: string;
  approxLength: number;
  color: 'sage' | 'tan';
};

const EDGES: EdgeData[] = EDGE_DEFS.map(([from, to, offset, color]) => {
  const { d, approxLength } = makePath(from, to, offset);
  return { id: `${from}-${to}`, from, to, d, approxLength, color };
});

// Bidirectional lookup
const EDGE_LOOKUP: Record<string, EdgeData> = {};
EDGES.forEach(e => {
  EDGE_LOOKUP[`${e.from}-${e.to}`] = e;
  EDGE_LOOKUP[`${e.to}-${e.from}`] = e;
});

const SEQUENCES: string[][] = [
  ['A','C','B','D','G','I','L','O','Q'],
  ['A','C','E','G','J','M','N','T'],
  ['F','S','H','K','T'],
  ['D','I','L','O','R','P','N'],
  ['B','E','H','S','F'],
  ['G','J','L','Q','R'],
  ['E','G','J','M','R','O'],
  ['A','F','S','K','N','T'],
  ['I','D','B','C','A'],
  ['L','M','N','K','H','E'],
];

const SEQ_DELAYS    = [0, 1200, 2400, 3800, 5200, 6400, 7600, 9000, 10400, 11800];
const CYCLE_MS      = 15000;
const STEP_MS       = 750;
const NODE_DUR_MS   = 800;
const EDGE_DUR_MS   = 900;
const EDGE_DELAY_MS = 120;

const PRIMARY_HUBS   = new Set<string>(['G']);
const SECONDARY_HUBS = new Set<string>(['B', 'D', 'I', 'L', 'O']);

// Color themes
const THEMES = {
  dark: {
    sageDim:    '#2A5A4E',
    tanDim:     '#2A3F5E',
    sageActive: '#34D399',
    tanActive:  '#60A5FA',
    fadeColor:  '#020617', // slate-950
    nodeFillSage: '#1E3028',
    nodeFillTan:  '#1A2535',
    hubFill:      '#1E4035',
    hubFill2:     '#1E3A2A',
    hubStroke:    '#3D7A6B',
    centerDot:    '#3D7A6B',
  },
  light: {
    sageDim:    '#8AA68E',
    tanDim:     '#B5A882',
    sageActive: '#6E9E72',
    tanActive:  '#C0A870',
    fadeColor:  '#FAF7F2', // cream-base
    nodeFillSage: '#C4D4C2',
    nodeFillTan:  '#E8DEC8',
    hubFill:      '#C4D4C2',
    hubFill2:     '#C4D4C2',
    hubStroke:    '#7A9E7E',
    centerDot:    '#5C8A60',
  },
} as const;

type Theme = keyof typeof THEMES;

// ── Component ────────────────────────────────────────────────────────────────

export default function HeroNetworkAnimation({ theme = 'dark' }: { theme?: Theme }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const c = THEMES[theme];

  useEffect(() => {
    if (!window.matchMedia('(prefers-reduced-motion: no-preference)').matches) return;

    const svg = svgRef.current;
    if (!svg) return;

    const timeouts: ReturnType<typeof setTimeout>[] = [];
    let cycleTimer: ReturnType<typeof setTimeout> | null = null;
    let effectCancelled = false;

    function activateNode(nodeId: string) {
      const fill = svg!.getElementById(`nf-${nodeId}`) as SVGCircleElement | null;
      const ring = svg!.getElementById(`nr-${nodeId}`) as SVGCircleElement | null;
      if (!fill) return;

      // Bright flash
      fill.style.transition = 'opacity 80ms ease';
      fill.style.opacity = '1';

      // Expanding ring pulse
      if (ring) {
        const baseR = PRIMARY_HUBS.has(nodeId) ? 6 : SECONDARY_HUBS.has(nodeId) ? 5 : 4;
        ring.style.transition = 'none';
        ring.setAttribute('r', String(baseR));
        ring.style.opacity = '0.9';
        const t1 = setTimeout(() => {
          if (effectCancelled) return;
          ring.style.transition = `r ${NODE_DUR_MS}ms ease-out, opacity ${NODE_DUR_MS}ms ease-out`;
          ring.setAttribute('r', String(baseR + 16));
          ring.style.opacity = '0';
        }, 40);
        timeouts.push(t1);
      }

      // Settle back to resting brightness
      const restOpacity = PRIMARY_HUBS.has(nodeId) ? '0.7'
        : SECONDARY_HUBS.has(nodeId) ? '0.6' : '0.5';
      const t2 = setTimeout(() => {
        if (effectCancelled) return;
        fill.style.transition = 'opacity 700ms ease';
        fill.style.opacity = restOpacity;
      }, NODE_DUR_MS);
      timeouts.push(t2);

      // Fully dim after rest period
      const dimOpacity = PRIMARY_HUBS.has(nodeId) ? '0.45'
        : SECONDARY_HUBS.has(nodeId) ? '0.4' : '0.35';
      const t3 = setTimeout(() => {
        if (effectCancelled) return;
        fill.style.transition = 'opacity 1000ms ease';
        fill.style.opacity = dimOpacity;
      }, NODE_DUR_MS + 1200);
      timeouts.push(t3);
    }

    function animatePulse(from: string, to: string) {
      const edge = EDGE_LOOKUP[`${from}-${to}`];
      if (!edge) return;
      const pathEl = svg!.getElementById(`edge-${edge.id}`) as SVGPathElement | null;
      if (!pathEl) return;

      const reversed   = edge.from !== from;
      const activeColor = edge.color === 'sage' ? c.sageActive : c.tanActive;
      const dimColor    = edge.color === 'sage' ? c.sageDim    : c.tanDim;

      // Glow the edge line while pulse travels
      pathEl.style.transition = 'none';
      pathEl.style.stroke      = activeColor;
      pathEl.style.opacity     = '0.7';
      pathEl.style.strokeWidth = '1.5';

      // Create the travelling dot
      const dot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      dot.setAttribute('r', '3.5');
      dot.setAttribute('fill', activeColor);
      dot.setAttribute('class', 'hna-pulse-dot');
      dot.style.filter = `drop-shadow(0 0 5px ${activeColor}) drop-shadow(0 0 10px ${activeColor})`;
      svg!.insertBefore(dot, svg!.querySelector('.hna-fade-overlay'));

      let totalLength: number;
      try { totalLength = pathEl.getTotalLength(); }
      catch { dot.remove(); return; }
      if (totalLength === 0) { dot.remove(); return; }

      const startTime = performance.now();

      function frame(now: number) {
        if (effectCancelled) { dot.remove(); return; }
        const t = Math.min((now - startTime) / EDGE_DUR_MS, 1);
        // Ease in-out quad
        const eased = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
        const dist = reversed ? totalLength * (1 - eased) : totalLength * eased;
        try {
          const pt = pathEl!.getPointAtLength(dist);
          dot.setAttribute('cx', pt.x.toFixed(1));
          dot.setAttribute('cy', pt.y.toFixed(1));
        } catch { /* ignore */ }

        if (t < 1) {
          requestAnimationFrame(frame);
        } else {
          dot.remove();
          if (!effectCancelled) {
            pathEl!.style.transition = 'opacity 800ms ease, stroke-width 600ms ease, stroke 500ms ease';
            pathEl!.style.opacity     = '0.22';
            pathEl!.style.strokeWidth = '0.9';
            pathEl!.style.stroke      = dimColor;
          }
        }
      }
      requestAnimationFrame(frame);
    }

    function runSequence(seq: string[]) {
      seq.forEach((nodeId, i) => {
        const t = setTimeout(() => {
          if (effectCancelled) return;
          activateNode(nodeId);
          if (i < seq.length - 1) {
            const t2 = setTimeout(() => {
              if (!effectCancelled) animatePulse(nodeId, seq[i + 1]);
            }, EDGE_DELAY_MS);
            timeouts.push(t2);
          }
        }, i * STEP_MS);
        timeouts.push(t);
      });
    }

    function startCycle() {
      SEQUENCES.forEach((seq, i) => {
        const t = setTimeout(() => { if (!effectCancelled) runSequence(seq); }, SEQ_DELAYS[i]);
        timeouts.push(t);
      });
      cycleTimer = setTimeout(startCycle, CYCLE_MS);
    }

    startCycle();

    return () => {
      effectCancelled = true;
      timeouts.forEach(clearTimeout);
      if (cycleTimer) clearTimeout(cycleTimer);
      svg.querySelectorAll('.hna-pulse-dot').forEach(el => el.remove());
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [theme]);

  return (
    <svg
      ref={svgRef}
      viewBox="0 0 800 480"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
      style={{
        position: 'absolute',
        inset: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        zIndex: 0,
      }}
    >
      <defs>
        <linearGradient id="hna-fade-left" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%"   stopColor={c.fadeColor} stopOpacity="1" />
          <stop offset="100%" stopColor={c.fadeColor} stopOpacity="0" />
        </linearGradient>
        <linearGradient id="hna-fade-right" x1="1" y1="0" x2="0" y2="0">
          <stop offset="0%"   stopColor={c.fadeColor} stopOpacity="1" />
          <stop offset="100%" stopColor={c.fadeColor} stopOpacity="0" />
        </linearGradient>
        <linearGradient id="hna-fade-top" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor={c.fadeColor} stopOpacity="1" />
          <stop offset="100%" stopColor={c.fadeColor} stopOpacity="0" />
        </linearGradient>
        <linearGradient id="hna-fade-bottom" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0%"   stopColor={c.fadeColor} stopOpacity="1" />
          <stop offset="100%" stopColor={c.fadeColor} stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* Base edges */}
      {EDGES.map(e => (
        <path
          key={e.id}
          id={`edge-${e.id}`}
          d={e.d}
          fill="none"
          stroke={e.color === 'sage' ? c.sageDim : c.tanDim}
          strokeWidth="1"
          opacity="0.28"
        />
      ))}

      {/* Nodes */}
      {NODES.map(n => {
        if (PRIMARY_HUBS.has(n.id)) {
          return (
            <g key={n.id}>
              <circle cx={n.cx} cy={n.cy} r={15} fill="none" stroke={c.sageDim}   strokeWidth="1" opacity="0.12" />
              <circle cx={n.cx} cy={n.cy} r={10} fill="none" stroke={c.sageDim}   strokeWidth="1" opacity="0.25" />
              <circle id={`nf-${n.id}`} cx={n.cx} cy={n.cy} r={6} fill={c.hubFill}  stroke={c.hubStroke} strokeWidth="1" opacity="0.55" />
              <circle id={`nr-${n.id}`} cx={n.cx} cy={n.cy} r={6} fill="none"        stroke={c.sageActive} strokeWidth="1.5" opacity="0" />
              <circle cx={n.cx} cy={n.cy} r={2} fill={c.centerDot} opacity="0.8" />
            </g>
          );
        }
        if (SECONDARY_HUBS.has(n.id)) {
          return (
            <g key={n.id}>
              <circle cx={n.cx} cy={n.cy} r={10} fill="none" stroke={c.sageDim}    strokeWidth="1" opacity="0.2" />
              <circle id={`nf-${n.id}`} cx={n.cx} cy={n.cy} r={5} fill={c.hubFill2} stroke={c.hubStroke} strokeWidth="1" opacity="0.5" />
              <circle id={`nr-${n.id}`} cx={n.cx} cy={n.cy} r={5} fill="none"         stroke={c.sageActive} strokeWidth="1.5" opacity="0" />
              <circle cx={n.cx} cy={n.cy} r={1.8} fill={c.centerDot} opacity="0.7" />
            </g>
          );
        }
        // Regular nodes — alternate sage/tan
        const useTan = ['F','J','M','P','R','T','N','Q'].includes(n.id);
        const nodeFill   = useTan ? c.nodeFillTan  : c.nodeFillSage;
        const nodeStroke = useTan ? c.tanDim        : c.sageDim;
        const nodeActive = useTan ? c.tanActive      : c.sageActive;
        return (
          <g key={n.id}>
            <circle id={`nf-${n.id}`} cx={n.cx} cy={n.cy} r={4} fill={nodeFill} stroke={nodeStroke} strokeWidth="1" opacity="0.45" />
            <circle id={`nr-${n.id}`} cx={n.cx} cy={n.cy} r={4} fill="none"     stroke={nodeActive} strokeWidth="1.5" opacity="0" />
            <circle cx={n.cx} cy={n.cy} r={1.5} fill={nodeStroke} opacity="0.6" />
          </g>
        );
      })}

      {/* Edge-fade overlays — pulse dots are inserted before these so they appear under the fades */}
      <g className="hna-fade-overlay">
        <rect x="0"   y="0"   width="180" height="480" fill="url(#hna-fade-left)"   />
        <rect x="620" y="0"   width="180" height="480" fill="url(#hna-fade-right)"  />
        <rect x="0"   y="0"   width="800" height="80"  fill="url(#hna-fade-top)"    />
        <rect x="0"   y="360" width="800" height="120" fill="url(#hna-fade-bottom)" />
      </g>
    </svg>
  );
}
