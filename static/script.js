function showSection(id) {
  const sections = document.querySelectorAll('.panel');
  sections.forEach((section) => section.classList.remove('active'));

  const target = document.getElementById(id);
  if (target) target.classList.add('active');

  document.querySelectorAll('.nav-link').forEach((button) => {
    const isActive = button.dataset.section === id;
    button.classList.toggle('active', isActive);
  });
}

function generateStudentNo() {
  const studentNo = Math.floor(100000 + Math.random() * 900000);
  const input = document.getElementById('student_no');
  if (input) input.value = studentNo;
}

document.addEventListener('DOMContentLoaded', () => {
  const defaultSection = document.body.dataset.defaultSection || 'login';
  const activeSection = document.querySelector('.panel.active')?.id || defaultSection;
  showSection(activeSection);

  document.querySelectorAll('.nav-link').forEach((button) => {
    button.addEventListener('click', () => {
      const target = button.dataset.section;
      if (target) showSection(target);
    });
  });

  const tabGroups = [
    {
      tabs: document.querySelectorAll('.admin-tab'),
      panels: document.querySelectorAll('.admin-panel'),
    },
    {
      tabs: document.querySelectorAll('.settings-tab'),
      panels: document.querySelectorAll('.settings-panel'),
    },
  ];

  tabGroups.forEach(({ tabs, panels }) => {
    tabs.forEach((tab) => {
      tab.addEventListener('click', () => {
        const target = tab.dataset.target;
        if (!target) return;

        tabs.forEach((item) => item.classList.toggle('active', item === tab));
        panels.forEach((panel) => {
          panel.classList.toggle('active', panel.id === target);
        });
      });
    });
  });

  const loginPanel = document.getElementById('login');
  if (loginPanel && !document.body.classList.contains('logged-in')) {
    showSection('login');
  }
});