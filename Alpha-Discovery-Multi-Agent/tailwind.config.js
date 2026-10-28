/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['class'],
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    container: {
      center: true,
      padding: { DEFAULT: '1rem', sm: '1.5rem', lg: '2rem' },
      screens: {
        '2xl': '1400px',
      },
    },
    extend: {
      fontFamily: {
        sans: ['Geist', 'system-ui', 'sans-serif'],
        heading: ['Instrument Serif', 'Georgia', 'serif'],
        mono: ['Geist Mono', 'ui-monospace', 'monospace'],
      },
      colors: {
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: '#050505',
        foreground: '#f8fafc',
        primary: {
          DEFAULT: '#2563eb',
          foreground: '#ffffff',
          light: '#3b82f6',
          dark: '#1d4ed8',
        },
        secondary: {
          DEFAULT: '#7c3aed',
          foreground: '#ffffff',
          light: '#8b5cf6',
          dark: '#6d28d9',
        },
        accent: {
          cyan: '#22d3ee',
          blue: '#38bdf8',
          purple: '#c084fc',
          emerald: '#34d399',
        },
        void: {
          950: '#030304',
          900: '#050505',
          850: '#09090b',
          800: '#0c0c0f',
          750: '#121217',
          700: '#181820',
          600: '#272733',
        },
        card: {
          DEFAULT: 'rgba(9, 9, 11, 0.75)',
          foreground: '#f8fafc',
          hover: 'rgba(12, 12, 15, 0.90)',
        },
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
      keyframes: {
        drift: { '0%': { transform: 'translate3d(0,0,0) scale(1)' }, '100%': { transform: 'translate3d(6vw,-4vh,0) scale(1.18)' } },
        marquee: { '0%': { transform: 'translateX(0)' }, '100%': { transform: 'translateX(-50%)' } },
        waveFlow: { '0%': { transform: 'translateX(0)' }, '100%': { transform: 'translateX(-50%)' } },
        'accordion-down': {
          from: { height: '0' },
          to: { height: 'var(--radix-accordion-content-height)' },
        },
        'accordion-up': {
          from: { height: 'var(--radix-accordion-content-height)' },
          to: { height: '0' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-10px)' },
        },
        pulseGlow: {
          '0%, 100%': { opacity: '0.4' },
          '50%': { opacity: '0.8' },
        },
        streamFlow: {
          '0%': { strokeDashoffset: '100' },
          '100%': { strokeDashoffset: '0' },
        },
      },
      animation: {
        drift: 'drift 22s ease-in-out infinite alternate',
        driftSlow: 'drift 34s ease-in-out infinite alternate-reverse',
        marquee: 'marquee 48s linear infinite',
        waveFlow: 'waveFlow 14s linear infinite',
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out',
        float: 'float 6s ease-in-out infinite',
        pulseGlow: 'pulseGlow 4s ease-in-out infinite',
        streamFlow: 'streamFlow 2s linear infinite',
      },
      boxShadow: {
        'glow-blue': '0 0 40px -10px rgba(37, 99, 235, 0.3)',
        'glow-purple': '0 0 40px -10px rgba(124, 58, 237, 0.3)',
        'glow-cyan': '0 0 40px -10px rgba(34, 211, 238, 0.3)',
        'glass-card': '0 8px 32px 0 rgba(0, 0, 0, 0.37)',
      },
    },
  },
  plugins: [],
};
