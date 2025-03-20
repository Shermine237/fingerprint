from odoo import api, fields, models, _
from datetime import datetime, timedelta
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)

class PointeurHrImportLine(models.Model):
    _name = 'pointeur_hr.import.line'
    _description = 'Import Line'
    _order = 'date, employee_name'

    import_id = fields.Many2one('pointeur_hr.import', string='Import', required=True, ondelete='cascade')
    employee_name = fields.Char(string='Imported Name', required=True)
    employee_id = fields.Many2one('hr.employee', string='Employee')
    display_id = fields.Char(string='Badge ID')
    payroll_id = fields.Char(string='Payroll ID')
    department = fields.Char(string='Department')
    dept_code = fields.Char(string='Department Code')
    date = fields.Date(string='Date', required=True)
    check_in = fields.Datetime(string='Check In')  # Non requis car peut être vide
    check_out = fields.Datetime(string='Check Out')
    in_note = fields.Char(string='Check In Note')
    out_note = fields.Char(string='Check Out Note')
    reg_hours = fields.Float(string='Regular Hours')
    ot1_hours = fields.Float(string='Overtime 1 Hours')
    ot2_hours = fields.Float(string='Overtime 2 Hours')
    total_hours = fields.Float(string='Total Hours', compute='_compute_hours')
    location_id = fields.Many2one('pointeur_hr.location', string='Attendance Location')
    attendance_id = fields.Many2one('hr.attendance', string='Attendance')
    error_message = fields.Text(string='Error Message')
    notes = fields.Text(string='Notes')

    state = fields.Selection([
        ('imported', 'Imported'),
        ('mapped', 'Mapped'),
        ('done', 'Done'),
        ('error', 'Error')
    ], string='State', default='imported', required=True)

    @api.model
    def create(self, vals):
        """Override creation to initialize state"""
        _logger.info("=== START CREATE IMPORT LINE ===")
        _logger.info("Received values: %s", vals)
        
        if vals.get('employee_id'):
            vals['state'] = 'mapped'
        else:
            vals['state'] = 'imported'
            
        _logger.info("=== END CREATE IMPORT LINE ===")
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
        """Override write to manage states and mappings"""
        
        # If updating employee_id, update state
        if 'employee_id' in vals:
            if vals.get('employee_id'):
                # Do not change state if already done
                if self.filtered(lambda l: l.state != 'done'):
                    vals['state'] = 'mapped'
            else:
                # Do not change state if already done
                if self.filtered(lambda l: l.state != 'done'):
                    vals['state'] = 'imported'
                    
        # If changing state to 'done', check that employee is defined
        if vals.get('state') == 'done':
            for record in self:
                if not (record.employee_id or vals.get('employee_id')):
                    raise ValidationError(_(
                        "Cannot mark as done a line without an associated employee"
                    ))
                    
        result = super().write(vals)
        
        # After update, create/update mappings if necessary
        if vals.get('employee_id'):
            for record in self:
                if record.employee_name:  # Check that name is not empty
                    employee = self.env['hr.employee'].browse(vals['employee_id'])
                    _logger.info("Searching for mapping for %s -> %s", 
                               record.employee_name, employee.name)
                    
                    # Search for an existing mapping (active or inactive)
                    mapping = self.env['pointeur_hr.employee.mapping'].search(
                        [('name', '=', record.employee_name),
                        ('employee_id', '=', vals['employee_id']),
                        '|',
                        ('active', '=', True),
                        ('active', '=', False)
                        ], limit=1)
                    
                    # Check if employee already has an active mapping with another name
                    existing_employee_mapping = self.env['pointeur_hr.employee.mapping'].search([
                        ('employee_id', '=', vals['employee_id']),
                        '|',
                        ('active', '=', True),
                        ('active', '=', False)
                    ], limit=1)
                    
                    if not mapping:
                        try:
                            # If employee already has an active mapping with another name, do not create a new mapping
                            if existing_employee_mapping and existing_employee_mapping.name != record.employee_name:
                                pass
                            else:
                                # Create a new mapping
                                mapping_vals = {
                                    'name': record.employee_name,
                                    'employee_id': vals['employee_id'],
                                    'import_id': record.import_id.id,
                                }
                                self.env['pointeur_hr.employee.mapping'].sudo().create(mapping_vals)
                        except Exception as e:
                            _logger.error("Error creating mapping: %s", str(e))
                            # Do not block the update of the line
                    else:
                        # Reactivate and update the usage counter
                        mapping.write({
                            'active': True,
                            'import_count': mapping.import_count + 1,
                            'last_used': fields.Datetime.now(),
                            'import_id': record.import_id.id
                        })
        
        return result

    def action_view_attendance(self):
        """View associated attendance"""
        self.ensure_one()
        if self.attendance_id:
            return {
                'name': _('Attendance'),
                'type': 'ir.actions.act_window',
                'res_model': 'hr.attendance',
                'view_mode': 'form',
                'res_id': self.attendance_id.id,
                'context': {'create': False}
            }
        return True

    @api.constrains('check_in', 'check_out')
    def _check_validity(self):
        """Check the validity of check-in and check-out times"""
        for record in self:
            if record.check_in and record.check_out and record.check_out < record.check_in:
                raise ValidationError(_('Check-out time cannot be earlier than check-in time.'))

    def find_employee_mapping(self):
        """Automatically search for employee mappings"""
        mapped_count = 0
        error_count = 0
        
        for record in self:
            if not record.employee_id and record.employee_name:
                try:
                    # First, search for an existing mapping
                    mapping = self.env['pointeur_hr.employee.mapping'].search([
                        ('name', '=', record.employee_name),
                        ('active', '=', True)
                    ], limit=1)
                    
                    if mapping:
                        record.write({
                            'employee_id': mapping.employee_id.id,
                            'state': 'mapped'
                        })
                        # Update the usage counter
                        mapping.write({
                            'import_count': mapping.import_count + 1,
                            'last_used': fields.Datetime.now()
                        })
                        mapped_count += 1
                        continue

                    # If no mapping is found, use the smart search
                    employee = self.env['pointeur_hr.import']._find_employee_by_name(record.employee_name)
                    if employee:
                        # Check if employee already has an active mapping
                        existing_employee = self.env['pointeur_hr.employee.mapping'].search([
                            ('employee_id', '=', employee.id),
                            ('active', '=', True)
                        ], limit=1)
                        
                        if existing_employee:
                            # Do not create a new mapping if employee already has an active mapping
                            record.write({
                                'state': 'error',
                                'notes': _("Employee '%s' already has an active mapping with name '%s'") % 
                                         (employee.name, existing_employee.name)
                            })
                            error_count += 1
                            continue

                        # Check if an inactive mapping exists for this combination
                        inactive = self.env['pointeur_hr.employee.mapping'].search([
                            ('name', '=', record.employee_name),
                            ('employee_id', '=', employee.id),
                            ('active', '=', False)
                        ], limit=1)
                        
                        if inactive:
                            # Reactivate the inactive mapping
                            inactive.write({
                                'active': True,
                                'import_count': inactive.import_count + 1,
                                'last_used': fields.Datetime.now()
                            })
                        else:
                            # Create a new mapping
                            self.env['pointeur_hr.employee.mapping'].create({
                                'name': record.employee_name,
                                'employee_id': employee.id,
                                'import_id': record.import_id.id
                            })

                        # Update the line
                        record.write({
                            'employee_id': employee.id,
                            'state': 'mapped'
                        })
                        mapped_count += 1

                except Exception as e:
                    record.write({
                        'state': 'error',
                        'notes': _("Error searching for mapping: %s") % str(e)
                    })
                    error_count += 1

        # Notification message
        if mapped_count > 0 and error_count == 0:
            message = _("%d mappings found successfully.") % mapped_count
            msg_type = 'success'
        elif mapped_count > 0 and error_count > 0:
            message = _("%d mappings found, %d errors.") % (mapped_count, error_count)
            msg_type = 'warning'
        elif mapped_count == 0 and error_count > 0:
            message = _("%d errors occurred while searching for mappings.") % error_count
            msg_type = 'danger'
        else:
            message = _("No mappings found.")
            msg_type = 'info'
            
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Mapping Search'),
                'message': message,
                'sticky': False,
                'type': msg_type,
                'next': {
                    'type': 'ir.actions.act_window',
                    'name': _('Lines with Errors'),
                    'res_model': 'pointeur_hr.import.line',
                    'view_mode': 'tree,form',
                    'domain': [
                        ('import_id', '=', self.import_id.id),
                        ('state', '=', 'error')
                    ],
                    'context': {'create': False}
                } if error_count > 0 else False
            }
        }

    def action_create_mapping(self):
        """Create a mapping for this line"""
        self.ensure_one()
        
        if not self.employee_id:
            raise UserError(_("You must first select an employee."))
            
        # Check if a mapping already exists for this name
        existing_name = self.env['pointeur_hr.employee.mapping'].search([
            ('name', '=', self.employee_name),
            ('active', '=', True)
        ], limit=1)
        
        if existing_name and existing_name.employee_id.id != self.employee_id.id:
            raise UserError(_(
                "An active mapping already exists for the name '%s' (associated with employee %s)."
            ) % (self.employee_name, existing_name.employee_id.name))
        
        # Check if employee already has a mapping
        existing_employee = self.env['pointeur_hr.employee.mapping'].search([
            ('employee_id', '=', self.employee_id.id),
            ('active', '=', True)
        ], limit=1)
        
        if existing_employee and existing_employee.name != self.employee_name:
            raise UserError(_(
                "Employee '%s' already has an active mapping with name '%s'."
            ) % (self.employee_id.name, existing_employee.name))
            
        # Check if an inactive mapping exists for this combination
        inactive = self.env['pointeur_hr.employee.mapping'].search([
            ('name', '=', self.employee_name),
            ('employee_id', '=', self.employee_id.id),
            ('active', '=', False)
        ], limit=1)
        
        if inactive:
            # Reactivate the inactive mapping
            inactive.write({
                'active': True,
                'last_used': fields.Datetime.now(),
                'import_count': inactive.import_count + 1
            })
            message = _("Mapping reactivated: %s -> %s") % (self.employee_name, self.employee_id.name)
        elif existing_name and existing_name.employee_id.id == self.employee_id.id:
            # Update the existing mapping
            existing_name.write({
                'last_used': fields.Datetime.now(),
                'import_count': existing_name.import_count + 1
            })
            message = _("Mapping updated: %s -> %s") % (self.employee_name, self.employee_id.name)
        else:
            # Create a new mapping
            self.env['pointeur_hr.employee.mapping'].create({
                'name': self.employee_name,
                'employee_id': self.employee_id.id,
                'import_id': self.import_id.id
            })
            message = _("New mapping created: %s -> %s") % (self.employee_name, self.employee_id.name)
            
        # Update the line state
        self.write({'state': 'mapped'})
        
        # Display a confirmation message
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Mapping Created'),
                'message': message,
                'sticky': False,
                'type': 'success',
            }
        }

    def action_reset(self):
        """Reset a line in error"""
        return self.write({
            'state': 'imported',
            'error_message': False,
            'notes': False,
            'employee_id': False,
            'attendance_id': False
        })
