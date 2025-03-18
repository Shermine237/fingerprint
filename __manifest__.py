{
    'name': 'Pointeur HR',
    'version': '14.0.1.1.0',
    'category': 'Human Resources',
    'summary': 'Gestion des présences avec localisation',
    'description': """
        Module de gestion des présences avec localisation
    """,
    'author': 'Shermine237',
    'website': 'https://github.com/Shermine237',
    'depends': ['base', 'hr_attendance', 'hr'],
    'data': [
        'security/ir.model.access.csv',
        'views/pointeur_hr_employee_views.xml',
        'views/pointeur_hr_attendance_views.xml',
        'views/pointeur_hr_attendance_report_views.xml',
        'views/pointeur_hr_location_views.xml',
        'views/pointeur_hr_import_views.xml',
        'views/pointeur_hr_employee_mapping_views.xml',
        'views/pointeur_hr_menus.xml',
        'reports/pointeur_hr_attendance_report_template.xml',
        'wizards/pointeur_hr_attendance_report_export_views.xml',
        'wizards/pointeur_hr_select_employees_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
    'auto_install': False,
}
