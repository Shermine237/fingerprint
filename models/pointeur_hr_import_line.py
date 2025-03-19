from odoo import api, fields, models, _
from datetime import datetime, timedelta
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)

class PointeurHrImportLine(models.Model):
    _name = 'pointeur_hr.import.line'
    _description = 'Ligne d\'import des données du pointeur'
    _order = 'date, employee_name'

    import_id = fields.Many2one('pointeur_hr.import', string='Import', required=True, ondelete='cascade')
    employee_name = fields.Char(string='Nom employé', required=True)
    employee_id = fields.Many2one('hr.employee', string='Employé correspondant')
    display_id = fields.Char(string='ID Badge')
    payroll_id = fields.Char(string='ID Paie')
    department = fields.Char(string='Département')
    dept_code = fields.Char(string='Code département')
    date = fields.Date(string='Date', required=True)
    check_in = fields.Datetime(string='Entrée')  # Non requis car peut être vide
    check_out = fields.Datetime(string='Sortie')
    in_note = fields.Char(string='Note entrée')
    out_note = fields.Char(string='Note sortie')
    reg_hours = fields.Float(string='Heures normales')
    ot1_hours = fields.Float(string='Heures sup. 1')
    ot2_hours = fields.Float(string='Heures sup. 2')
    total_hours = fields.Float(string='Total heures', compute='_compute_hours')
    location_id = fields.Many2one('pointeur_hr.location', string='Lieu de pointage')
    attendance_id = fields.Many2one('hr.attendance', string='Présence')
    error_message = fields.Text(string='Message d\'erreur')
    notes = fields.Text(string='Notes')

    state = fields.Selection([
        ('imported', 'Importé'),
        ('mapped', 'Correspondance trouvée'),
        ('done', 'Terminé'),
        ('error', 'Erreur')
    ], string='État', default='imported', required=True)

    @api.model
    def create(self, vals):
        """Surcharge de la création pour initialiser l'état"""
        _logger.info("=== DÉBUT CREATE IMPORT LINE ===")
        _logger.info("Valeurs reçues : %s", vals)
        
        if vals.get('employee_id'):
            vals['state'] = 'mapped'
        else:
            vals['state'] = 'imported'
            
        _logger.info("=== FIN CREATE IMPORT LINE ===")
        return super().create(vals)

    @api.depends('check_in', 'check_out')
    def _compute_hours(self):
        for line in self:
            if line.check_in and line.check_out:
                delta = line.check_out - line.check_in
                line.total_hours = delta.total_seconds() / 3600.0
            else:
                line.total_hours = 0.0

    def write(self, vals):
        """Surcharge de l'écriture pour gérer les états et les correspondances"""
        _logger.info("=== DÉBUT WRITE IMPORT LINE ===")
        _logger.info("Valeurs reçues : %s", vals)
        
        # Si on met à jour l'employee_id, on met à jour l'état
        if 'employee_id' in vals:
            if vals.get('employee_id'):
                # Ne pas changer l'état si déjà terminé
                if self.filtered(lambda l: l.state != 'done'):
                    vals['state'] = 'mapped'
                    _logger.info("Mise à jour état : mapped")
            else:
                # Ne pas changer l'état si déjà terminé
                if self.filtered(lambda l: l.state != 'done'):
                    vals['state'] = 'imported'
                    _logger.info("Mise à jour état : imported (employee_id vide)")
                    
        # Si on change l'état en 'done', vérifier que l'employé est défini
        if vals.get('state') == 'done':
            for record in self:
                if not (record.employee_id or vals.get('employee_id')):
                    raise ValidationError(_(
                        "Impossible de marquer comme terminé une ligne sans employé associé"
                    ))
                    
        result = super().write(vals)
        
        # Après la mise à jour, créer/mettre à jour les correspondances si nécessaire
        if vals.get('employee_id'):
            for record in self:
                if record.employee_name:  # Vérifier que le nom n'est pas vide
                    employee = self.env['hr.employee'].browse(vals['employee_id'])
                    _logger.info("Recherche correspondance pour %s -> %s", 
                               record.employee_name, employee.name)
                    
                    # Rechercher une correspondance existante (active ou inactive)
                    mapping = self.env['pointeur_hr.employee.mapping'].search(
                        [('name', '=', record.employee_name),
                        ('employee_id', '=', vals['employee_id']),
                        '|',
                        ('active', '=', True),
                        ('active', '=', False)
                        ], limit=1)
                    
                    # Vérifier si l'employé a déjà une correspondance avec un autre nom
                    existing_employee_mapping = self.env['pointeur_hr.employee.mapping'].search([
                        ('employee_id', '=', vals['employee_id']),
                        '|',
                        ('active', '=', True),
                        ('active', '=', False)
                    ], limit=1)
                    
                    if not mapping:
                        try:
                            # Si l'employé a déjà une correspondance avec un autre nom, ne pas créer de nouvelle correspondance
                            if existing_employee_mapping and existing_employee_mapping.name != record.employee_name:
                                pass
                            else:
                                # Créer une nouvelle correspondance
                                mapping_vals = {
                                    'name': record.employee_name,
                                    'employee_id': vals['employee_id'],
                                    'import_id': record.import_id.id,
                                }
                                self.env['pointeur_hr.employee.mapping'].sudo().create(mapping_vals)
                        except Exception as e:
                            _logger.error("Erreur création correspondance : %s", str(e))
                            # Ne pas bloquer la mise à jour de la ligne
                    else:
                        # Réactiver et mettre à jour le compteur d'utilisation
                        mapping.write({
                            'active': True,
                            'import_count': mapping.import_count + 1,
                            'last_used': fields.Datetime.now(),
                            'import_id': record.import_id.id
                        })
        
        _logger.info("=== FIN WRITE IMPORT LINE ===")
        return result

    def action_view_attendance(self):
        """Voir la présence associée"""
        self.ensure_one()
        if self.attendance_id:
            return {
                'name': _('Présence'),
                'type': 'ir.actions.act_window',
                'res_model': 'hr.attendance',
                'view_mode': 'form',
                'res_id': self.attendance_id.id,
            }
        return True

    @api.constrains('check_in', 'check_out')
    def _check_validity(self):
        """ Vérifie la validité des heures d'entrée et de sortie """
        for record in self:
            if record.check_in and record.check_out and record.check_out < record.check_in:
                raise ValidationError(_('La date/heure de sortie ne peut pas être antérieure à la date/heure d\'entrée.'))

    def find_employee_mapping(self):
        """Recherche automatique des correspondances employés"""
        for record in self:
            if not record.employee_id and record.employee_name:
                # Chercher d'abord dans les correspondances existantes
                mapping = self.env['pointeur_hr.employee.mapping'].search(
                    [('name', '=', record.employee_name)], limit=1)
                if mapping:
                    record.write({'employee_id': mapping.employee_id.id})
                    continue

                # Si pas de correspondance, utiliser la recherche intelligente
                employee = self.env['pointeur_hr.import']._find_employee_by_name(record.employee_name)
                if employee:
                    record.write({'employee_id': employee.id})
        
        # Message de notification
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Recherche de correspondance'),
                'message': _('Recherche terminée.'),
                'sticky': False,
                'type': 'info',
            }
        }
    
    def action_create_mapping(self):
        """Créer une correspondance pour cette ligne"""
        self.ensure_one()
        
        if not self.employee_id:
            raise UserError(_("Vous devez d'abord sélectionner un employé."))
            
        # Vérifier si une correspondance existe déjà
        existing = self.env['pointeur_hr.employee.mapping'].search([
            ('name', '=', self.employee_name)
        ], limit=1)
        
        if existing:
            # Mettre à jour la correspondance existante
            existing.write({
                'employee_id': self.employee_id.id,
                'last_used': fields.Datetime.now(),
                'import_count': existing.import_count + 1
            })
            message = _("Correspondance mise à jour : %s -> %s") % (self.employee_name, self.employee_id.name)
        else:
            # Créer une nouvelle correspondance
            self.env['pointeur_hr.employee.mapping'].create({
                'name': self.employee_name,
                'employee_id': self.employee_id.id,
                'import_id': self.import_id.id,
            })
            message = _("Nouvelle correspondance créée : %s -> %s") % (self.employee_name, self.employee_id.name)
            
        # Mettre à jour l'état de la ligne
        self.write({'state': 'mapped'})
        
        # Afficher un message de confirmation
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Correspondance créée'),
                'message': message,
                'sticky': False,
                'type': 'success',
            }
        }

    def action_reset(self):
        """Réinitialiser une ligne en erreur"""
        return self.write({
            'state': 'imported',
            'error_message': False,
            'notes': False,
            'employee_id': False,
            'attendance_id': False
        })
