from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.translate import _

class PointeurHrEmployeeMapping(models.Model):
    _name = 'pointeur_hr.employee.mapping'
    _description = 'Correspondance des noms importés avec les employés'
    _rec_name = 'imported_name'

    imported_name = fields.Char(string='Nom importé', required=True, index=True)
    employee_id = fields.Many2one('hr.employee', string='Employé', required=True)
    last_used = fields.Datetime(string='Dernière utilisation', default=fields.Datetime.now)
    import_count = fields.Integer(string='Nombre d\'imports', default=1)
    similarity_score = fields.Float(string='Score de similarité', compute='_compute_similarity_score')
    auto_created = fields.Boolean(string='Créé automatiquement')
    parent_mapping_id = fields.Many2one('pointeur_hr.employee.mapping', string='Correspondance parente')
    import_ids = fields.Many2many('pointeur_hr.import', string='Imports', compute='_compute_import_ids')

    _sql_constraints = [
        ('unique_imported_name', 'unique(imported_name)', 
         'Une correspondance existe déjà pour ce nom importé !')
    ]

    def name_get(self):
        return [(rec.id, f"{rec.imported_name} → {rec.employee_id.name}") for rec in self]

    def _compute_similarity_score(self):
        """Calcule le score de similarité entre le nom importé et le nom de l'employé"""
        for record in self:
            if record.imported_name and record.employee_id:
                record.similarity_score = self.env['pointeur_hr.import']._name_similarity_score(
                    record.imported_name, record.employee_id.name)
            else:
                record.similarity_score = 0

    def action_find_similar_names(self):
        """Recherche d'autres noms similaires qui pourraient correspondre au même employé"""
        self.ensure_one()
        if not self.employee_id:
            raise UserError(_("Vous devez d'abord sélectionner un employé."))
            
        # Recherche des correspondances existantes
        other_mappings = self.search([
            ('employee_id', '=', self.employee_id.id),
            ('id', '!=', self.id)
        ])
        
        # Recherche des lignes d'import avec des noms similaires
        import_lines = self.env['pointeur_hr.import.line'].search([
            ('employee_name', '!=', self.imported_name),
            ('employee_id', '=', False)
        ], limit=100)
        
        similar_names = []
        for line in import_lines:
            score = self.env['pointeur_hr.import']._name_similarity_score(
                self.imported_name, line.employee_name)
            if score >= 0.5:  # Seuil de similarité
                similar_names.append((line, score))
                
        # Trier par score de similarité
        similar_names.sort(key=lambda x: x[1], reverse=True)
        
        # Construire le message
        message = _("<h3>Noms similaires pour '{}'</h3>").format(self.imported_name)
        
        # Ajouter les correspondances existantes
        if other_mappings:
            message += _("<h4>Autres correspondances pour cet employé :</h4><ul>")
            for mapping in other_mappings:
                message += _("<li>{} (utilisé {} fois)</li>").format(
                    mapping.imported_name, mapping.import_count)
            message += "</ul>"
            
        # Ajouter les noms similaires trouvés
        if similar_names:
            message += _("<h4>Noms similaires trouvés dans les imports :</h4><ul>")
            for line, score in similar_names[:10]:  # Limiter aux 10 meilleurs
                message += _("<li>{} (score : {:.2f}) - <a href='#' data-oe-model='pointeur_hr.import.line' data-oe-id='{}'>Voir</a></li>").format(
                    line.employee_name, score, line.id)
            message += "</ul>"
            
            # Ajouter un bouton pour créer des correspondances automatiquement
            message += _("<p><a class='btn btn-primary' href='/web#action=create_similar_mappings&mapping_id={}'>Créer les correspondances pour les noms similaires</a></p>").format(self.id)
        else:
            message += _("<p>Aucun nom similaire trouvé.</p>")
            
        # Afficher le message
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Recherche de noms similaires'),
                'message': message,
                'sticky': True,
                'type': 'info',
            }
        }
    
    def action_create_similar_mappings(self):
        """Crée des correspondances pour tous les noms similaires"""
        self.ensure_one()
        if not self.employee_id:
            raise UserError(_("Vous devez d'abord sélectionner un employé."))
            
        # Recherche des lignes d'import avec des noms similaires
        import_lines = self.env['pointeur_hr.import.line'].search([
            ('employee_name', '!=', self.imported_name),
            ('employee_id', '=', False)
        ], limit=100)
        
        created_count = 0
        for line in import_lines:
            score = self.env['pointeur_hr.import']._name_similarity_score(
                self.imported_name, line.employee_name)
            if score >= 0.7:  # Seuil plus élevé pour la création automatique
                # Vérifier si une correspondance existe déjà
                existing = self.search([('imported_name', '=', line.employee_name)], limit=1)
                if not existing:
                    # Créer une nouvelle correspondance
                    self.create({
                        'imported_name': line.employee_name,
                        'employee_id': self.employee_id.id,
                        'auto_created': True,
                        'parent_mapping_id': self.id
                    })
                    created_count += 1
                    
                    # Mettre à jour la ligne d'import
                    line.write({
                        'employee_id': self.employee_id.id,
                        'state': 'mapped'
                    })
        
        # Message de confirmation
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Création de correspondances'),
                'message': _('%d nouvelles correspondances créées.') % created_count,
                'sticky': False,
                'type': 'success',
            }
        }

    def _compute_import_ids(self):
        for record in self:
            # Rechercher les lignes d'import qui utilisent cette correspondance
            import_lines = self.env['pointeur_hr.import.line'].search([
                ('employee_name', '=', record.imported_name),
                ('employee_id', '=', record.employee_id.id)
            ])
            # Récupérer les imports associés
            record.import_ids = import_lines.mapped('import_id')
