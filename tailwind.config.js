/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.{jinja,html}",
    "./apps/**/*.py",
    "./core/**/*.py",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
