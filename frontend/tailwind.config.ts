import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: '#0b0e14',
        dock: '#0d1117',
        panel: '#161b22',
        card: '#1c2128',
        raised: '#21262d',
        line: '#30363d',
        'line-strong': '#484f58',
        ink: '#e6edf3',
        muted: '#94a3b8',
        telemetry: '#38bdf8',
        'telemetry-deep': '#0284c7',
        nominal: '#10b981',
        warning: '#f59e0b',
        critical: '#ef4444',
        simulated: '#64748b',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      borderRadius: { technical: '4px' },
      boxShadow: { panel: '0 8px 24px rgba(0, 0, 0, 0.24)' },
    },
  },
  plugins: [],
} satisfies Config;
