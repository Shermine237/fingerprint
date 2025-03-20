{
    'name': 'Attendance Manager HR',
    'version': '14.0.1.1.0',
    'category': 'Human Resources',
    'summary': 'Location-based attendance management',
    'description': """
        Location-based attendance management module
    """,
    'author': 'Shermine237',
    'website': 'https://github.com/Shermine237',
    'depends': ['base', 'hr_attendance', 'hr'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/pointeur_hr_location_views.xml',
        'views/pointeur_hr_import_views.xml',
        'views/pointeur_hr_import_line_views.xml',  
        'views/pointeur_hr_employee_mapping_views.xml',
        'views/pointeur_hr_employee_views.xml',
        'views/pointeur_hr_attendance_views.xml',
        'views/pointeur_hr_attendance_report_views.xml',
        'views/pointeur_hr_menus.xml',
        'reports/pointeur_hr_attendance_report_template.xml',
        'wizards/pointeur_hr_attendance_report_export_views.xml',
        'wizards/pointeur_hr_select_employees_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'pointeur_hr/static/src/js/import_form_view.js',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
    'auto_install': False,
}
