// Manejo de temas para el formulario SNMP - Versión simplificada
(function($) {
    'use strict';

    // Función para configurar tema oscuro dinámico
    function setupDarkTheme() {
        // Detectar preferencia de tema del sistema
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)');
        
        // Función para aplicar tema
        function applyTheme(isDark) {
            if (isDark) {
                document.documentElement.classList.add('dark-theme');
            } else {
                document.documentElement.classList.remove('dark-theme');
            }
        }
        
        // Detectar si Django Admin ya tiene tema oscuro aplicado
        function detectDjangoTheme() {
            const dataTheme = document.documentElement.getAttribute('data-theme');
            return dataTheme === 'dark';
        }
        
        // Aplicar tema basado en Django Admin primero, luego en preferencias del sistema
        if (detectDjangoTheme()) {
            applyTheme(true);
        } else if (prefersDark.matches) {
            applyTheme(true);
        } else {
            applyTheme(false);
        }
        
        // Escuchar cambios de tema del sistema
        prefersDark.addEventListener('change', function(e) {
            if (!detectDjangoTheme()) {
                applyTheme(e.matches);
            }
        });
        
        // Detectar tema desde localStorage si está disponible
        const savedTheme = localStorage.getItem('admin-theme');
        if (savedTheme) {
            applyTheme(savedTheme === 'dark');
        }
    }

    // Función para verificar el estado del tema
    function debugTheme() {
        const dataTheme = document.documentElement.getAttribute('data-theme');
        const hasDarkClass = document.documentElement.classList.contains('dark-theme');
        const bodyClasses = document.body.className;
        
        console.log('🐛 Debug del tema:');
        console.log('  - data-theme:', dataTheme);
        console.log('  - dark-theme class:', hasDarkClass);
        console.log('  - body classes:', bodyClasses);
    }

    // Exponer funciones globalmente para depuración
    window.debugTheme = debugTheme;
    window.setupDarkTheme = setupDarkTheme;

    // Inicializar cuando el documento esté listo
    $(document).ready(function() {
        setupDarkTheme();
    });

})(django.jQuery);
