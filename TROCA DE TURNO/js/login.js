const form = document.querySelector('#login-form');
const errorBox = document.querySelector('#auth-error');
const submitButton = document.querySelector('#submit-button');

function showError(message) {
  errorBox.textContent = message;
  errorBox.hidden = !message;
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  showError('');
  submitButton.disabled = true;

  try {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: document.querySelector('#name').value.trim(),
        password: document.querySelector('#password').value
      })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Não foi possível entrar.');
    window.location.href = '/';
  } catch (error) {
    showError(error.message || 'Não foi possível entrar.');
  } finally {
    submitButton.disabled = false;
  }
});
