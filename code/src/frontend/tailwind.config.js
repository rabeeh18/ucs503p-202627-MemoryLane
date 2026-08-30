/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{svelte,js,ts}'],
  theme: {
    extend: {
      colors: {
        'bg-dark': '#1a1a1a',
        'text-primary': '#ffffff',
        'text-secondary': '#999999',
        'text-tertiary': '#666666',
        'accent': '#4a9eff'
      }
    }
  },
  plugins: []
};
