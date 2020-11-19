import unittest

from apiserver.search import parse_query


class TestSearch(unittest.TestCase):
    def test_simple(self):
        main, sup, sup_filters, vars = parse_query({
            'keywords': ['green', 'taxi'],
            'source': 'gov',
        })
        self.assertEqual(
            main,
            [
                {
                    'multi_match': {
                        'query': 'green taxi',
                        'operator': 'and',
                        'type': 'cross_fields',
                        'fields': ['id^10', 'description', 'name^3', 'attribute_keywords'],
                    },
                },
                {
                    'bool': {
                        'filter': [
                            {
                                'terms': {
                                    'source': ['gov'],
                                },
                            },
                        ],
                    },
                },
            ],
        )
        self.assertEqual(
            sup,
            [
                {
                    'multi_match': {
                        'query': 'green taxi',
                        'operator': 'and',
                        'type': 'cross_fields',
                        'fields': [
                            'dataset_id^10',
                            'dataset_description',
                            'dataset_name^3',
                            'dataset_attribute_keywords',
                        ],
                    },
                },
            ],
        )
        self.assertEqual(
            sup_filters,
            [
                {
                    'terms': {
                        'dataset_source': ['gov'],
                    },
                },
            ],
        )
        self.assertEqual(vars, [])

    def test_types(self):
        main, sup, sup_filters, vars = parse_query({
            'keywords': ['food'],
            'types': ['spatial', 'temporal'],
        })

        self.assertEqual(
            main,
            [
                {
                    'multi_match': {
                        'query': 'food',
                        'operator': 'and',
                        'type': 'cross_fields',
                        'fields': [
                            'id^10',
                            'description',
                            'name^3',
                            'attribute_keywords',
                        ],
                    },
                },
                {
                    'bool': {
                        'filter': [
                            {
                                'terms': {
                                    'types': ['spatial', 'temporal'],
                                },
                            },
                        ],
                    },
                },
            ],
        )
        self.assertEqual(
            sup,
            [
                {
                    'multi_match': {
                        'query': 'food',
                        'type': 'cross_fields',
                        'operator': 'and',
                        'fields': [
                            'dataset_id^10',
                            'dataset_description',
                            'dataset_name^3',
                            'dataset_attribute_keywords',
                        ],
                    },
                },
            ],
        )
        self.assertEqual(
            sup_filters,
            [
                {
                    'terms': {
                        'dataset_types': ['spatial', 'temporal'],
                    },
                },
            ],
        )
        self.assertEqual(vars, [])

    def test_ranges(self):
        main, sup, sup_filters, vars = parse_query({
            'keywords': ['green', 'taxi'],
            'source': ['gov'],
            'variables': [
                {
                    'type': 'temporal_variable',
                    'start': '2019-01-01',
                    'end': '2019-12-31',
                },
                {
                    'type': 'geospatial_variable',
                    'latitude1': 45.4,
                    'latitude2': 50.6,
                    'longitude1': -73.2,
                    'longitude2': -75.8,
                },
            ],
        })
        self.assertEqual(
            main,
            [
                {
                    'multi_match': {
                        'query': 'green taxi',
                        'operator': 'and',
                        'type': 'cross_fields',
                        'fields': ['id^10', 'description', 'name^3', 'attribute_keywords'],
                    },
                },
                {
                    'bool': {
                        'filter': [
                            {
                                'terms': {
                                    'source': ['gov'],
                                },
                            },
                        ],
                    },
                },
                {
                    'nested': {
                        'path': 'columns',
                        'query': {
                            'bool': {
                                'must': [
                                    {
                                        'term': {
                                            'columns.semantic_types': 'http://schema.org/DateTime',
                                        },
                                    },
                                    {
                                        'nested': {
                                            'path': 'columns.coverage',
                                            'query': {
                                                'range': {
                                                    'columns.coverage.range': {
                                                        'gte': 1546300800.0,
                                                        'lte': 1577750400.0,
                                                        'relation': 'intersects',
                                                    },
                                                },
                                            },
                                        },
                                    },
                                ],
                            },
                        },
                    },
                },
                {
                    'nested': {
                        'path': 'spatial_coverage.ranges',
                        'query': {
                            'bool': {
                                'filter': {
                                    'geo_shape': {
                                        'spatial_coverage.ranges.range': {
                                            'shape': {
                                                'type': 'envelope',
                                                'coordinates': [
                                                    [-75.8, 50.6],
                                                    [-73.2, 45.4],
                                                ],
                                            },
                                            'relation': 'intersects',
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            ],
        )
