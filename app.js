const layer = document.querySelector('#layer');
const details = document.querySelector('.details h3');
layer?.addEventListener('change', () => {
  details.textContent = 'Insufficient data';
});
