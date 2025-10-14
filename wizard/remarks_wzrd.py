from odoo import models, fields

class RemarksWizard(models.TransientModel):
    _name = 'remarks.wizard'
    _description = 'Remarks Wizard'

    remarks = fields.Text(string="Description", readonly=True)

    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self.env.context.get('active_id')
        if active_id:
            record = self.env['res.approvers'].browse(active_id)
            res['remarks'] = record.remarks or "No description available."
        return res