"""package."""
from collections import defaultdict
from copy import copy, deepcopy
from typing import Any, Dict, List

import logging

from pydantic import BaseModel

from pfb_fhir.model import TransformerContext

logger = logging.getLogger(__name__)


class ContextSimplifier(object):
    """Simplify flattened properties."""

    @staticmethod
    def simplify(context: TransformerContext) -> TransformerContext:
        """

        :rtype: object
        """
        assert context.properties
        simplified_properties = ContextSimplifier._group_by_root(context)
        simplified_properties = ContextSimplifier._extensions(simplified_properties)
        simplified_properties = ContextSimplifier._single_item_lists(simplified_properties)
        simplified_properties = ContextSimplifier._codings(simplified_properties)
        # logger.info([p.flattened_key for p in context.properties.values()])
        context.properties = {}
        for k, properties in simplified_properties.items():
            for p in properties:
                context.properties[p.flattened_key] = p
        return context

    @staticmethod
    def _group_by_root(context: TransformerContext) -> Dict[str, list]:
        """Gather flattened properties to original key."""
        simplified_properties = defaultdict(list)
        for property_ in context.properties.values():
            simplified_properties[property_.leaf_elements[0]['id']].append(property_)
        return simplified_properties

    @staticmethod
    def _single_item_lists(simplified_properties: Dict[str, List]) -> Dict[str, List]:
        """Simplify values with single item lists."""
        # values single item array
        # inspect 3x to get embedded single item lists
        for i in range(3):
            logger.debug(f"iterate {i}")
            for k, properties in simplified_properties.items():
                flattened_keys = [p.flattened_key for p in properties]
                for flattened_key in flattened_keys:
                    flattened_key_parts = flattened_key.split('.')
                    array_index = -1
                    if '0' in flattened_key_parts:
                        array_index = flattened_key_parts.index('0')
                    if array_index > 0:
                        property_name = flattened_key_parts[array_index - 1]
                        if not any([f"{property_name}.1" in k for k in flattened_keys]):
                            logger.debug(f"{property_name}.0  in {flattened_key} is a single item list")
                            for p in properties:
                                # replace first occurrence of index in property name
                                p.flattened_key = p.flattened_key.replace(f"{property_name}.0", property_name, 1)
                simplified_properties[k] = properties

        return simplified_properties

    @staticmethod
    def _extensions(simplified_properties: Dict[str, List]) -> Dict[str, List]:
        """Simplify values with extensions."""
        simplified_extensions = []
        simplified_extensions_key = None
        for k, properties in simplified_properties.items():
            if not k.endswith('extension'):
                continue
            simplified_extensions_key = k
            extension_index = 0
            while True:
                flattened_keys = [p.flattened_key for p in properties if
                                  p.flattened_key.startswith(f"extension.{extension_index}")]
                if len(flattened_keys) == 0:
                    break

                url_property = next(
                    iter([p for p in properties if p.flattened_key == f"extension.{extension_index}.url"]))
                extension_name = url_property.value.split('/')[-1]
                sub_extension_index = 0
                while True:
                    sub_extension_flattened_keys = [p.flattened_key for p in properties if
                                                    f"extension.{extension_index}.extension.{sub_extension_index}" in p.flattened_key]
                    if len(sub_extension_flattened_keys) == 0:
                        break
                    sub_extension_url_property = next(
                        iter([p for p in properties if
                              p.flattened_key == f"extension.{extension_index}.extension.{sub_extension_index}.url"]))
                    sub_extension_name = sub_extension_url_property.value.split('/')[-1]
                    sub_extension_value = next(
                        iter([p for p in properties if
                              p.flattened_key == f"extension.{extension_index}.extension.{sub_extension_index}.valueCoding.code"]),
                        None)
                    if not sub_extension_value:
                        sub_extension_value = next(
                            iter([p for p in properties if
                                  p.flattened_key == f"extension.{extension_index}.extension.{sub_extension_index}.valueString"]),
                            None)

                    # logger.info(f"{extension_name}.{sub_extension_name} = {sub_extension_value.value}")
                    simplified_extension = deepcopy(sub_extension_value)
                    simplified_extension.flattened_key = f"{extension_name}.{sub_extension_name}"
                    simplified_extensions.append(simplified_extension)
                    sub_extension_index += 1

                extension_index += 1

        if simplified_extensions_key:
            del simplified_properties[simplified_extensions_key]
            simplified_properties[simplified_extensions_key] = simplified_extensions

        return simplified_properties

    @staticmethod
    def _codings(simplified_properties: Dict[str, List]) -> Dict[str, List]:
        """Values with codings (just look at first level of dict for coding)."""
        original_coded_values = defaultdict(list)
        for k, properties in simplified_properties.items():
            flattened_keys = [p.flattened_key for p in properties if 'coding' in p.flattened_key]
            simplified_coding_values = []
            if len(flattened_keys) > 0:
                system = next(iter([k for k in flattened_keys if k.endswith('.coding.system')]), None)
                code = next(iter([k for k in flattened_keys if k.endswith('.coding.code')]), None)
                display = next(iter([k for k in flattened_keys if k.endswith('.coding.display')]), None)
                if system:
                    original_coded_values[k].append(system)
                    system = next(iter([p for p in properties if p.flattened_key == system]), None)
                if code:
                    original_coded_values[k].append(code)
                    code = next(iter([p for p in properties if p.flattened_key == code]), None)
                if display:
                    original_coded_values[k].append(display)
                    display = next(iter([p for p in properties if p.flattened_key == display]), None)
                if system and code:
                    base_key = system.flattened_key.replace('.coding.system', '')
                    system_value = system.value.split('/')[-1]
                    # logger.info(f"{base_key}.{system_value} = {code.value}")
                    simplified_coding = deepcopy(code)
                    simplified_coding.flattened_key = f"{base_key}.{system_value}"
                    simplified_coding_values.append(simplified_coding)
                if system and display:
                    base_key = system.flattened_key.replace('.coding.system', '')
                    display_value = display.value
                    # logger.info(f"{base_key}.{system_value}.display = {display_value}")
                    simplified_coding = deepcopy(display)
                    simplified_coding.flattened_key = f"{base_key}.{system_value}.display"
                    simplified_coding_values.append(simplified_coding)
            simplified_properties[k].extend(simplified_coding_values)
        for k, original_coded_values in original_coded_values.items():
            simplified_properties[k] = [p for p in simplified_properties[k] if
                                        p.flattened_key not in original_coded_values]
        return simplified_properties
