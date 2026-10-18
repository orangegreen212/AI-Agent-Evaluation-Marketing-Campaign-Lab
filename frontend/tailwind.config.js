/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Surface system — deep technical dark
        surface: {
          950: '#070a10',
          900: '#0b1017',
          850: '#0f1620',
          800: '#141c27',
          750: '#1a2330',
          700: '#212c3b',
          600: '#2c3849',
          500: '#3a4759',
        },
        // Accent — restrained cyan/teal for a lab/engineering feel
        accent: {
          50: '#ecfeff',
          100: '#cffafe',
          200: '#a5f3fc',
          300: '#67e8f9',
          400: '#22d3ee',
          500: '#06b6d4',
          600: '#0891b2',
          700: '#0e7490',
          800: '#155e75',
          900: '#164e63',
        },
        // Status
        success: {
          400: '#34d399',
          500: '#10b981',
          600: '#059669',
          700: '#047857',
          900: '#064e3b',
        },
        warning: {
          400: '#fbbf24',
          500: '#f59e0b',
          600: '#d97706',
          700: '#b45309',
          900: '#78350f',
        },
        danger: {
          400: '#f87171',
          500: '#ef4444',
          600: '#dc2626',
          700: '#b91c1c',
          900: '#7f1d1d',
        },
        // Neutral text
        ink: {
          50: '#f1f5f9',
          100: '#e2e8f0',
          200: '#cbd5e1',
          300: '#94a3b8',
          400: '#64748b',
          500: '#475569',
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem' }],
      },
      boxShadow: {
        'glow-accent': '0 0 0 1px rgba(34,211,238,0.18), 0 8px 30px -12px rgba(34,211,238,0.25)',
        'glow-danger': '0 0 0 1px rgba(239,68,68,0.2), 0 8px 30px -12px rgba(239,68,68,0.25)',
        panel: '0 1px 0 0 rgba(255,255,255,0.02) inset, 0 12px 40px -20px rgba(0,0,0,0.7)',
      },
      keyframes: {
        'fade-in': {
          '0%': { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'pulse-soft': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.55' },
        },
        'shimmer': {
          '100%': { transform: 'translateX(100%)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.3s ease-out',
        'pulse-soft': 'pulse-soft 1.6s ease-in-out infinite',
        'shimmer': 'shimmer 1.6s infinite',
      },
    },
  },
  plugins: [],
};
