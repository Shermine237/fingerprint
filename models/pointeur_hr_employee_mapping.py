from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)

class PointeurHrEmployeeMapping(models.Model):
    _name = 'pointeur_hr.employee.mapping'
    _description = 'Correspondance des noms importés avec les employés'
    _order = 'last_used desc, import_count desc'

    name = fields.Char(string='Nom importé', required=True, index=True)
    employee_id = fields.Many2one('hr.employee', string='Employé', required=True)
    last_used = fields.Datetime(string='Dernière utilisation', default=fields.Datetime.now)
    import_count = fields.Integer(string='Nombre d\'imports', default=1)
    import_id = fields.Many2one('pointeur_hr.import', string='Import d\'origine')
    import_ids = fields.Many2many('pointeur_hr.import', string='Imports', compute='_compute_import_ids')
    active = fields.Boolean(string='Actif', default=True)

    _sql_constraints = [
        ('unique_name_active', 'unique(name, active)',
         'Une correspondance existe déjà pour ce nom importé !'),
        ('unique_employee_active', 'unique(employee_id, active)',
         'Cet employé a déjà une correspondance de nom active !')
    ]

    @api.constrains('name', 'employee_id', 'active')
    def _check_unique_constraints(self):
        """Vérification supplémentaire pour éviter les doublons"""
        for record in self:
            if not record.active:
                continue  # Ignorer les enregistrements inactifs
                
            # Vérifier si un autre enregistrement actif existe avec le même nom
            same_name = self.search([
                ('id', '!=', record.id),
                ('name', '=', record.name),
                ('active', '=', True)
            ], limit=1)
            
            if same_name:
                raise ValidationError(_(
                    "Une correspondance active existe déjà pour le nom '%s' (associée à l'employé %s)."
                ) % (record.name, same_name.employee_id.name))
            
            # Vérifier si un autre enregistrement actif existe pour le même employé
            same_employee = self.search([
                ('id', '!=', record.id),
                ('employee_id', '=', record.employee_id.id),
                ('active', '=', True)
            ], limit=1)
            
            if same_employee:
                raise ValidationError(_(
                    "L'employé '%s' a déjà une correspondance active avec le nom '%s'."
                ) % (record.employee_id.name, same_employee.name))

    @api.model_create_multi
    def create(self, vals_list):
        """Surcharge de la création pour vérifier les doublons et logger"""
        result = self.env['pointeur_hr.employee.mapping']
        
        for vals in vals_list:
            _logger.info("Création correspondance : %s -> %s", 
                        vals.get('name'), vals.get('employee_id'))
            
            # Vérifier si une correspondance avec le même nom existe déjà
            existing_name = self.search([
                ('name', '=', vals.get('name')),
                ('active', '=', True)
            ], limit=1)
            
            if existing_name:
                _logger.warning("Une correspondance active existe déjà pour le nom '%s'", vals.get('name'))
                continue
                
            # Vérifier si l'employé a déjà une correspondance active
            existing_employee = self.search([
                ('employee_id', '=', vals.get('employee_id')),
                ('active', '=', True)
            ], limit=1)
            
            if existing_employee:
                _logger.warning("L'employé a déjà une correspondance active avec le nom '%s'", existing_employee.name)
                continue
                
            # Vérifier si une correspondance inactive existe pour cette combinaison
            inactive = self.search([
                ('name', '=', vals.get('name')),
                ('employee_id', '=', vals.get('employee_id')),
                ('active', '=', False)
            ], limit=1)
            
            if inactive:
                _logger.info("Réactivation correspondance existante")
                inactive.write({
                    'active': True,
                    'import_count': inactive.import_count + 1,
                    'last_used': fields.Datetime.now()
                })
                result |= inactive
            else:
                # Créer une nouvelle correspondance
                record = super(PointeurHrEmployeeMapping, self).create([vals])[0]
                result |= record
                
        return result

    def name_get(self):
        return [(rec.id, f"{rec.name} → {rec.employee_id.name}") for rec in self]

    def action_find_similar_names(self):
        """Recherche d'autres noms qui correspondent au même employé"""
        self.ensure_one()
        _logger.info("Recherche noms similaires pour %s", self.name)
        
        if not self.employee_id:
            raise UserError(_("Vous devez d'abord sélectionner un employé."))
            
        # Recherche des correspondances existantes pour cet employé
        other_mappings = self.search([
            ('employee_id', '=', self.employee_id.id),
            ('id', '!=', self.id),
            ('active', '=', True)
        ])
        _logger.info("Autres correspondances trouvées : %d", len(other_mappings))
        
        # Recherche des lignes d'import avec le même nom
        import_lines = self.env['pointeur_hr.import.line'].search([
            ('employee_name', '=', self.name),
            ('employee_id', '=', False),
            ('state', '!=', 'done')
        ], limit=10)
        _logger.info("Lignes sans correspondance trouvées : %d", len(import_lines))
        
        # Construire le message
        message_parts = []
        message_parts.append(_("<h3>Informations pour '{}'</h3>").format(self.name))
        
        # Ajouter les correspondances existantes
        if other_mappings:
            message_parts.append(_("<h4>Autres noms utilisés pour cet employé :</h4><ul>"))
            for mapping in other_mappings:
                message_parts.append(_("<li>{} (utilisé {} fois)</li>").format(
                    mapping.name, mapping.import_count))
            message_parts.append("</ul>")
        
        # Ajouter les lignes d'import sans correspondance
        if import_lines:
            message_parts.append(_("<h4>Lignes d'import sans correspondance :</h4><ul>"))
            for line in import_lines:
                message_parts.append(_("<li>Import #{} - {} ({})</li>").format(
                    line.import_id.id, line.employee_name, 
                    line.check_in.strftime('%d/%m/%Y') if line.check_in else ''))
            message_parts.append("</ul>")
            
        message = ''.join(message_parts)
        _logger.info("Message généré : %s", message)
            
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Analyse des correspondances'),
                'message': message,
                'sticky': True,
                'type': 'info',
                'next': {
                    'type': 'ir.actions.act_window',
                    'name': _('Lignes sans correspondance'),
                    'res_model': 'pointeur_hr.import.line',
                    'view_mode': 'tree,form',
                    'domain': [
                        ('employee_name', '=', self.name),
                        ('employee_id', '=', False),
                        ('state', '!=', 'done')
                    ],
                }
            }
        }
        
    def _compute_import_ids(self):
        """Calcule les imports qui ont utilisé cette correspondance"""
        for rec in self:
            import_lines = self.env['pointeur_hr.import.line'].search([
                ('employee_name', '=', rec.name),
                ('employee_id', '=', rec.employee_id.id)
            ])
            rec.import_ids = import_lines.mapped('import_id')
            
    def action_view_imports(self):
        """Voir les imports qui ont utilisé cette correspondance"""
        self.ensure_one()
        _logger.info("Affichage imports pour correspondance %s", self.name)
        
        return {
            'name': _('Imports'),
            'type': 'ir.actions.act_window',
            'res_model': 'pointeur_hr.import',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.import_ids.ids)],
        }
        
    def action_deactivate(self):
        """Désactiver une correspondance"""
        self.ensure_one()
        _logger.info("Désactivation correspondance %s", self.name)
        
        self.write({'active': False})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Correspondance désactivée'),
                'message': _("La correspondance '{}' a été désactivée").format(self.name),
                'sticky': False,
                'type': 'success'
            }
        }
