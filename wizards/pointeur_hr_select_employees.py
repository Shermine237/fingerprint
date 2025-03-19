from odoo import api, fields, models, _
from odoo.exceptions import UserError
from collections import defaultdict
import logging

_logger = logging.getLogger(__name__)

class PointeurHrSelectEmployees(models.TransientModel):
    _name = 'pointeur_hr.select.employees'
    _description = 'Assistant de sélection des employés'
    
    import_id = fields.Many2one('pointeur_hr.import', string='Import', required=True)
    line_ids = fields.One2many('pointeur_hr.select.employees.line', 'wizard_id', string='Lignes')
    mapped_count = fields.Integer(string='Lignes déjà mappées', readonly=True)
    unmapped_count = fields.Integer(string='Lignes à traiter', compute='_compute_unmapped_count')
    
    @api.depends('line_ids')
    def _compute_unmapped_count(self):
        for wizard in self:
            wizard.unmapped_count = len(wizard.line_ids)
    
    @api.model
    def default_get(self, fields_list):
        res = super(PointeurHrSelectEmployees, self).default_get(fields_list)
        if self.env.context.get('active_model') == 'pointeur_hr.import' and self.env.context.get('active_id'):
            import_id = self.env.context.get('active_id')
            import_record = self.env['pointeur_hr.import'].browse(import_id)
            
            # Vérifier qu'il y a des lignes sans correspondance
            unmapped_lines = import_record.line_ids.filtered(lambda l: not l.employee_id and l.state != 'done')
            if not unmapped_lines:
                return res
                
            res['import_id'] = import_id
            
            # Regrouper les lignes par nom d'employé
            lines_by_name = defaultdict(list)
            for line in unmapped_lines:
                if line.employee_name:  # S'assurer que le nom n'est pas vide
                    lines_by_name[line.employee_name].append(line)
            
            # Créer une seule ligne de wizard par nom d'employé
            line_vals = []
            for employee_name, lines in lines_by_name.items():
                # Prendre la première ligne comme référence
                reference_line = lines[0]
                line_vals.append((0, 0, {
                    'employee_name': employee_name,
                    'line_count': len(lines),
                    'reference_line_id': reference_line.id,
                    'import_line_ids': [(6, 0, [l.id for l in lines])],
                    'check_in': reference_line.check_in,
                    'check_out': reference_line.check_out,
                }))
            
            res['line_ids'] = line_vals
            res['mapped_count'] = len(import_record.line_ids) - len(unmapped_lines)
            
        return res
    
    def action_confirm(self):
        """Confirmer les sélections et créer les présences"""
        self.ensure_one()
        _logger.info("=== DÉBUT CONFIRMATION WIZARD ===")
        
        if not self.line_ids:
            raise UserError(_("Aucune ligne à traiter."))
            
        # Compter les nouvelles correspondances créées
        manual_mapped_count = 0
        mapped_names = []
        mapping_errors = []
        
        # Mettre à jour les lignes d'import avec les employés sélectionnés
        valid_lines = self.line_ids.filtered(lambda l: l.employee_name and l.employee_id)
        _logger.info("Nombre de lignes valides : %d", len(valid_lines))
        
        if not valid_lines:
            raise UserError(_("Aucun employé sélectionné."))
        
        for wizard_line in valid_lines:
            try:
                _logger.info("Traitement de la ligne pour %s -> %s", 
                            wizard_line.employee_name, wizard_line.employee_id.name)
                
                # Mettre à jour toutes les lignes d'import associées
                import_lines = wizard_line.import_line_ids
                if not import_lines:
                    _logger.warning("Aucune ligne d'import associée pour %s", wizard_line.employee_name)
                    continue
                    
                _logger.info("Mise à jour de %d lignes d'import", len(import_lines))
                import_lines.write({
                    'employee_id': wizard_line.employee_id.id,
                    'state': 'mapped'
                })
                manual_mapped_count += len(import_lines)
                mapped_names.append(wizard_line.employee_name)
                
                # Créer une correspondance permanente si demandé
                if wizard_line.create_mapping:
                    _logger.info("Création de la correspondance pour %s -> %s", 
                               wizard_line.employee_name, wizard_line.employee_id.name)
                    
                    # Vérifier si une correspondance existe déjà
                    mapping = self.env['pointeur_hr.employee.mapping'].sudo().search([
                        ('name', '=', wizard_line.employee_name),
                        ('employee_id', '=', wizard_line.employee_id.id),
                        '|',
                        ('active', '=', True),
                        ('active', '=', False)
                    ], limit=1)
                    
                    if mapping:
                        _logger.info("Une correspondance existe déjà (ID: %s)", mapping.id)
                        # Réactiver et mettre à jour si nécessaire
                        mapping.sudo().write({
                            'active': True,
                            'import_count': mapping.import_count + 1,
                            'last_used': fields.Datetime.now(),
                            'import_id': self.import_id.id
                        })
                    else:
                        # Créer la nouvelle correspondance
                        mapping_vals = {
                            'name': wizard_line.employee_name,
                            'employee_id': wizard_line.employee_id.id,
                            'import_id': self.import_id.id,
                        }
                        _logger.info("Création nouvelle correspondance : %s", mapping_vals)
                        mapping = self.env['pointeur_hr.employee.mapping'].sudo().create(mapping_vals)
                        _logger.info("Correspondance créée avec succès (ID: %s)", mapping.id)
                        
            except Exception as e:
                error_msg = str(e)
                _logger.error("Erreur lors du traitement de %s: %s", wizard_line.employee_name, error_msg)
                mapping_errors.append(f"{wizard_line.employee_name}: {error_msg}")
                # Ne pas interrompre le traitement des autres lignes
                continue
        
        # Calculer les noms non mappés (seulement ceux qui ont un nom)
        unmapped_lines = self.line_ids.filtered(lambda l: l.employee_name and not l.employee_id)
        unmapped_names = [line.employee_name for line in unmapped_lines]
        _logger.info("Noms non mappés : %s", unmapped_names)
        
        # Créer les présences seulement s'il y a des lignes mappées
        total_mapped = self.mapped_count + manual_mapped_count
        if total_mapped > 0:
            _logger.info("Création des présences pour %d lignes", total_mapped)
            self.import_id._create_attendances(total_mapped)
        
        # Créer le message de retour
        message_parts = []
        if mapped_names:
            message_parts.append(_("%d lignes ont été mappées pour %d noms") % (manual_mapped_count, len(mapped_names)))
            if self.mapped_count > 0:
                message_parts.append(_("%d lignes étaient déjà mappées") % self.mapped_count)
        if unmapped_names:
            message_parts.append(_("%d noms restent non mappés : %s") % (len(unmapped_names), ", ".join(unmapped_names)))
        if mapping_errors:
            message_parts.append(_("Erreurs lors de la création des correspondances :\n%s") % "\n".join(mapping_errors))
            
        message = _("Résultat du mapping :\n- %s") % "\n- ".join(message_parts)
        _logger.info(message)
        
        # Afficher le message à l'utilisateur
        self.env['bus.bus']._sendone(self.env.user.partner_id, 'notification', {
            'type': 'info',
            'title': _("Résultat du mapping"),
            'message': message,
            'sticky': True
        })
        
        _logger.info("=== FIN CONFIRMATION WIZARD ===")
        return self.import_id._create_attendances(total_mapped)


class PointeurHrSelectEmployeesLine(models.TransientModel):
    _name = 'pointeur_hr.select.employees.line'
    _description = 'Ligne de l\'assistant de sélection des employés'
    
    wizard_id = fields.Many2one('pointeur_hr.select.employees', string='Assistant', required=True, ondelete='cascade')
    reference_line_id = fields.Many2one('pointeur_hr.import.line', string='Ligne de référence', required=True)
    import_line_ids = fields.Many2many('pointeur_hr.import.line', string='Lignes d\'import associées')
    employee_name = fields.Char(string='Nom importé', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employé')
    check_in = fields.Datetime(string='Entrée (exemple)', readonly=True)
    check_out = fields.Datetime(string='Sortie (exemple)', readonly=True)
    create_mapping = fields.Boolean(string='Créer correspondance', default=True)
    line_count = fields.Integer(string='Nombre de lignes', readonly=True)
