from odoo import models, fields

class PointeurHrAttendanceReportExport(models.TransientModel):
    _name = 'pointeur_hr.attendance.report.export.wizard'
    _description = 'Assistant d\'export du rapport de présence'

    export_type = fields.Selection([
        ('excel', 'Excel'),
        ('pdf', 'PDF')
    ], string='Type d\'export', default='excel', required=True)

    def action_export(self):
        active_ids = self.env.context.get('active_ids', [])
        
        # Si aucune ligne n'est sélectionnée, exporter toutes les lignes
        if not active_ids:
            active_ids = self.env['pointeur_hr.attendance.report'].search([]).ids
            
        records = self.env['pointeur_hr.attendance.report'].browse(active_ids)

        # Filtrer les enregistrements sans heure d'entrée
        records = records.filtered(lambda r: r.check_in)

        if self.export_type == 'excel':
            return records.action_export_xlsx()
        else:
            return records.action_export_pdf()
