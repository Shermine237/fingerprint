odoo.define('pointeur_hr.attendance_report_tree', function (require) {
    "use strict";

    const core = require('web.core');
    const ListController = require('web.ListController');
    const ListView = require('web.ListView');
    const viewRegistry = require('web.view_registry');

    const QWeb = core.qweb;
    const _t = core._t;

    const PointeurHrAttendanceReportController = ListController.extend({
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

    const PointeurHrAttendanceReportListView = ListView.extend({
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
