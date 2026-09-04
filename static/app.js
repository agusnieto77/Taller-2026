document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.label-form').forEach((form) => {
    const buttons = [...form.querySelectorAll('button[name="value"]')];
    let submitting = false;

    const submitChoice = (button) => {
      if (submitting || button.disabled) return;
      button.click();
    };

    document.addEventListener('keydown', (event) => {
      if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      const activeTag = document.activeElement?.tagName;
      if (activeTag === 'INPUT' || activeTag === 'TEXTAREA' || activeTag === 'SELECT') return;
      const button = buttons.find((candidate) => candidate.dataset.shortcut === event.key);
      if (button) {
        event.preventDefault();
        submitChoice(button);
      }
    });

    form.addEventListener('submit', (event) => {
      if (submitting) {
        event.preventDefault();
        return;
      }
      if (form.dataset.existing === 'true' && !window.confirm('Esta nota ya tiene una clasificación. ¿Querés reemplazarla?')) {
        event.preventDefault();
        return;
      }
      submitting = true;
      form.setAttribute('aria-busy', 'true');
      form.classList.add('is-submitting');
      window.setTimeout(() => {
        buttons.forEach((button) => { button.disabled = true; });
      }, 0);
    });
  });
});
