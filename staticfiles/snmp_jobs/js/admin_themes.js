// Manejo de temas para el formulario SNMP
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
                console.log('🌙 Aplicando tema oscuro');
            } else {
                document.documentElement.classList.remove('dark-theme');
                console.log('☀️ Aplicando tema claro');
            }
        }
        
        // Detectar si Django Admin ya tiene tema oscuro aplicado
        function detectDjangoTheme() {
            // Verificar si el documento tiene data-theme="dark"
            const dataTheme = document.documentElement.getAttribute('data-theme');
            const hasDjangoDarkTheme = dataTheme === 'dark';
            
            console.log('🔍 Detectando tema Django:', dataTheme, 'Es oscuro:', hasDjangoDarkTheme);
            return hasDjangoDarkTheme;
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
            // Solo cambiar si Django Admin no tiene tema manual
            if (!detectDjangoTheme()) {
                applyTheme(e.matches);
            }
        });
        
        // Detectar tema desde localStorage si está disponible
        const savedTheme = localStorage.getItem('admin-theme');
        if (savedTheme) {
            applyTheme(savedTheme === 'dark');
        }
        
        // Observar cambios en el DOM para detectar cambios de tema de Django Admin
        const observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.type === 'attributes' && 
                    (mutation.attributeName === 'data-theme' || mutation.attributeName === 'class')) {
                    console.log('🔄 Cambio detectado en:', mutation.attributeName);
                    if (detectDjangoTheme()) {
                        applyTheme(true);
                    } else if (!prefersDark.matches) {
                        applyTheme(false);
                    }
                }
            });
        });
        
        observer.observe(document.documentElement, {
            attributes: true,
            attributeFilter: ['data-theme', 'class']
        });
        
        observer.observe(document.body, {
            attributes: true,
            attributeFilter: ['class']
        });
        
        // Verificación única después de 1 segundo
        setTimeout(function() {
            if (detectDjangoTheme()) {
                applyTheme(true);
            }
        }, 1000);
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
        
        // Verificar si los estilos se están aplicando
        const testElement = document.querySelector('.form-row');
        if (testElement) {
            const computedStyle = window.getComputedStyle(testElement);
            console.log('  - form-row background:', computedStyle.backgroundColor);
            console.log('  - form-row color:', computedStyle.color);
        }
    }

    // Exponer funciones globalmente para depuración
    window.debugTheme = debugTheme;
    window.setupDarkTheme = setupDarkTheme;

    // Inicializar cuando el documento esté listo
    $(document).ready(function() {
        setupDarkTheme();
    });

})(django.jQuery);
