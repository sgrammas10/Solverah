/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        display: ['"Playfair Display"', 'Georgia', 'serif'],
        sans: ['"DM Sans"', 'system-ui', 'sans-serif'],
      },
      colors: {
        cream: {
          base: '#FAF7F2',
          subtle: '#EAE4DB',
          muted: '#D4CFC8',
        },
        forest: {
          dark: '#1B4332',
          mid: '#2D6A4F',
          light: '#40916C',
          pale: '#D8F3DC',
        },
        ink: {
          primary: '#1A1A1A',
          secondary: '#555555',
          tertiary: '#888888',
        },
      },
      keyframes: {
        fadeUp: {
          '0%': { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
      },
      animation: {
        'fade-up': 'fadeUp 0.6s ease-out forwards',
        'fade-up-slow': 'fadeUp 0.6s ease-out 0.15s forwards',
        'fade-up-slower': 'fadeUp 0.6s ease-out 0.3s forwards',
        'fade-in': 'fadeIn 0.4s ease-out forwards',
      },
    },
  },
  plugins: [],
};
