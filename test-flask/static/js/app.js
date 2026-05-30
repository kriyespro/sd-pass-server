// Auto-reset add forms after submit
document.querySelectorAll('form[method="post"]').forEach(form => {
  if (form.querySelector('input[name="name"]')) {
    form.addEventListener('submit', function() {
      setTimeout(() => this.reset(), 100);
    });
  }
});

// Highlight newest list items on load
const firstItems = document.querySelectorAll('.contact-item:first-child, .lead-item:first-child, .deal-item:first-child');
firstItems.forEach(el => {
  el.style.borderColor = '#818cf8';
  setTimeout(() => { el.style.borderColor = ''; }, 2000);
});
