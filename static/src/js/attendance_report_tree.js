odoo.define('pointeur_hr.attendance_report_tree', function (require) {
    "use strict";

    var core = require('web.core');
    var ListController = require('web.ListController');
    var ListView = require('web.ListView');
    var viewRegistry = require('web.view_registry');
    var _t = core._t;

    var PointeurHrAttendanceReportController = ListController.extend({
        buttons_template: 'pointeur_hr.AttendanceReportButtons',

        renderButtons: function () {
            this._super.apply(this, arguments);
            if (this.$buttons) {
                this.$buttons.find('.o_list_button_export').on('click', this._onExportReport.bind(this));
            }
        },

        _onExportReport: function () {
            this.do_action({
                type: 'ir.actions.act_window',
                name: _t('Export du rapport'),
                res_model: 'pointeur_hr.attendance.report.export.wizard',
                views: [[false, 'form']],
                target: 'new',
                context: {
                    active_model: 'pointeur_hr.attendance.report',
                    search_domain: this.model.get(this.handle, {raw: true}).domain || [],
                }
            });
        }
    });

    var PointeurHrAttendanceReportListView = ListView.extend({
        config: _.extend({}, ListView.prototype.config, {
            Controller: PointeurHrAttendanceReportController,
        }),
    });

    viewRegistry.add('attendance_report_tree', PointeurHrAttendanceReportListView);

    return {
        PointeurHrAttendanceReportController: PointeurHrAttendanceReportController,
        PointeurHrAttendanceReportListView: PointeurHrAttendanceReportListView,
    };
});
