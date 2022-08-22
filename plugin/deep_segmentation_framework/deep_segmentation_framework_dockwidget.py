# -*- coding: utf-8 -*-
"""
/***************************************************************************
 DeepSegmentationFrameworkDockWidget
                                 A QGIS plugin
 This plugin allows to perform segmentation with deep neural networks
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                             -------------------
        begin                : 2022-08-11
        git sha              : $Format:%H$
        copyright            : (C) 2022 by Przemyslaw Aszkowski
        email                : przemyslaw.aszkowski@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
import enum
import logging
import os
from dataclasses import dataclass
import onnxruntime as ort

from qgis.PyQt.QtWidgets import QComboBox
from qgis.PyQt import QtGui, QtWidgets, uic
from qgis.PyQt.QtCore import pyqtSignal
from qgis._core import QgsMapLayerProxyModel
from qgis.core import QgsVectorLayer
from qgis.core import QgsRasterLayer
from qgis.core import QgsMessageLog
from qgis.core import QgsProject
from qgis.core import QgsVectorLayer
from qgis.core import Qgis
from qgis.PyQt.QtWidgets import QInputDialog, QLineEdit, QFileDialog

from deep_segmentation_framework.common.defines import PLUGIN_NAME, LOG_TAB_NAME, ConfigEntryKey
from deep_segmentation_framework.common.inference_parameters import InferenceParameters, ProcessedAreaType

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'deep_segmentation_framework_dockwidget_base.ui'))


class OperationFailedException(Exception):
    pass


class DeepSegmentationFrameworkDockWidget(QtWidgets.QDockWidget, FORM_CLASS):

    closingPlugin = pyqtSignal()
    run_inference_signal = pyqtSignal(InferenceParameters)

    def __init__(self, iface, parent=None):
        """Constructor."""
        super(DeepSegmentationFrameworkDockWidget, self).__init__(parent)
        self.iface = iface
        self.setupUi(self)
        self._create_connections()
        QgsMessageLog.logMessage("Widget setup", LOG_TAB_NAME, level=Qgis.Info)
        self._setup_misc_ui()

    def _setup_misc_ui(self):
        combobox = self.comboBox_processedAreaSelection
        for name in ProcessedAreaType.get_all_names():
            combobox.addItem(name)

        model_path = ConfigEntryKey.MODEL_FILE_PATH.get()
        self.lineEdit_modelPath.setText(model_path)
        self._load_model_and_display_info(model_path)

        self.mMapLayerComboBox_inputLayer.setFilters(QgsMapLayerProxyModel.RasterLayer)
        self.mMapLayerComboBox_areaMaskLayer.setFilters(QgsMapLayerProxyModel.VectorLayer)
        self._set_processed_area_mask_options()

    def _set_processed_area_mask_options(self):
        show_mask_combobox = (self.get_selected_processed_area_type() == ProcessedAreaType.FROM_POLYGONS)
        self.mMapLayerComboBox_areaMaskLayer.setVisible(show_mask_combobox)

    def get_selected_processed_area_type(self) -> ProcessedAreaType:
        combobox = self.comboBox_processedAreaSelection  # type: QComboBox
        txt = combobox.currentText()
        return ProcessedAreaType(txt)

    def _create_connections(self):
        self.pushButton_run_inference.clicked.connect(self._run_inference)
        self.pushButton_browseModelPath.clicked.connect(self._browse_model_path)
        self.comboBox_processedAreaSelection.currentIndexChanged.connect(self._set_processed_area_mask_options)

    def _browse_model_path(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            'Select Model ONNX file...',
            os.path.expanduser('~'),
            'All files (*.*);; ONNX files (*.onnx)')
        if file_path:
            self.lineEdit_modelPath.setText(file_path)
            ConfigEntryKey.MODEL_FILE_PATH.set(file_path)
            self._load_model_and_display_info(file_path)

    def _load_model_and_display_info(self, file_path):
        """
        Tries to load the model and display its message.
        """

        input_size_px = 1
        txt = ''
        if file_path:
            try:
                sess = ort.InferenceSession(file_path)
                input_0 = sess.get_inputs()[0]
                txt += f'Input shape: {input_0.shape}   =   [BATCH_SIZE * CHANNELS * SIZE * SIZE]'
                input_size_px = input_0.shape[-1]

                # TODO idk how variable input will be handled
                self.spinBox_tileSize_px.setValue(input_size_px)
                self.spinBox_tileSize_px.setEnabled(False)
            except:
                txt = "Error! Failed to load the model!\nModel may be not usable"
                logging.exception(txt)
                self.spinBox_tileSize_px.setEnabled(True)

        self.label_modelInfo.setText(txt)

    def get_mask_layer_id(self):
        if not self.get_selected_processed_area_type() == ProcessedAreaType.FROM_POLYGONS:
            return None

        mask_layer_id = self.mMapLayerComboBox_areaMaskLayer.currentLayer().id()
        return mask_layer_id

    def get_inference_parameters(self) -> InferenceParameters:
        postprocessing_dilate_erode_size = self.spinBox_dilateErodeSize.value() \
                                         if self.checkBox_removeSmallAreas.isChecked() else 0
        processed_area_type = self.get_selected_processed_area_type()
        model_file_path = self.lineEdit_modelPath.text()
        self._load_model_and_display_info(model_file_path)

        inference_parameters = InferenceParameters(
            resolution_cm_per_px=self.doubleSpinBox_resolution_cm_px.value(),
            tile_size_px=self.spinBox_tileSize_px.value(),
            processed_area_type=processed_area_type,
            mask_layer_id=self.get_mask_layer_id(),
            input_layer_id=self.mMapLayerComboBox_inputLayer.currentLayer().id(),
            postprocessing_dilate_erode_size=postprocessing_dilate_erode_size,
            model_file_path=model_file_path,
        )
        return inference_parameters

    def _run_inference(self):
        try:
            inference_parameters = self.get_inference_parameters()
        except OperationFailedException as e:
            msg = str(e)
            self.iface.messageBar().pushMessage(PLUGIN_NAME, msg, level=Qgis.Warning)
            return

        self.run_inference_signal.emit(inference_parameters)

    def closeEvent(self, event):
        self.closingPlugin.emit()
        event.accept()

