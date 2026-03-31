// ─── Table Search Filter ────────────────────────────────────
function filterTable() {
  const input = document.getElementById('searchInput');
  if (!input) return;
  const filter = input.value.toUpperCase();
  const table = document.getElementById('ordersTable');
  if (!table) return;
  const rows = table.getElementsByTagName('tr');
  for (let i = 1; i < rows.length; i++) {
    const cells = rows[i].getElementsByTagName('td');
    let match = false;
    for (let j = 0; j < cells.length; j++) {
      if (cells[j].textContent.toUpperCase().includes(filter)) {
        match = true; break;
      }
    }
    rows[i].style.display = match ? '' : 'none';
  }
}

// ─── Auto-dismiss alerts after 4 seconds ────────────────────
document.addEventListener('DOMContentLoaded', function () {
  const alerts = document.querySelectorAll('.alert');
  alerts.forEach(function (el) {
    setTimeout(function () {
      el.style.transition = 'opacity .5s';
      el.style.opacity = '0';
      setTimeout(function () { el.remove(); }, 500);
    }, 4000);
  });

  // Highlight updated row if any URL param exists
  const url = new URL(window.location.href);
  // Track input uppercase auto-format
  const trackInput = document.getElementById('trackInput');
  if (trackInput) {
    trackInput.addEventListener('input', function () {
      const pos = this.selectionStart;
      this.value = this.value.toUpperCase();
      this.setSelectionRange(pos, pos);
    });
  }
});
