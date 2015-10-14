#!/usr/bin/env python

import sys
import argparse
from argparse import ArgumentError
from variation.vcf import VCFParser
from variation.variations.vars_matrices import VariationsH5
from variation import PRE_READ_MAX_SIZE


def _setup_argparse(**kwargs):
    'It prepares the command line argument parsing.'
    parser = argparse.ArgumentParser(**kwargs)

    parser.add_argument('input', type=argparse.FileType('rb'),
                        help='Input VCF file (default STDIN)',
                        default=sys.stdin, nargs=1)
    parser.add_argument('-o', '--output', required=True,
                        help='Output HDF5 file path')
    help_msg = 'Ignore SNPs with a number of alleles higher than --alt_gt_num'
    parser.add_argument('-i', '--ingnore_alt', action='store_true',
                        default=False, help=help_msg)
    parser.add_argument('-a', '--alt_gt_num', default=None, type=int,
                        help='Max number of alternative genotypes per variant')
    parser.add_argument('-p', '--pre_read_max_size', default=PRE_READ_MAX_SIZE,
                        help='Max number of records to get alt_gt_num',
                        type=int)
    parser.add_argument('-kf', '--kept fields', default=None, action='append',
                        help='Fields to write to HDF5 file (all fields)')
    parser.add_argument('-if', '--ignored fields', default=None,
                        action='append',
                        help='Fields to avoid writing to HDF5 file (None)')
    return parser


def _parse_args(parser):
    parsed_args = parser.parse_args()
    args = {}
    args['in_fhand'] = parsed_args.input[0]
    args['out_fpath'] = parsed_args.output
    if parsed_args.ignore_alt:
        if parsed_args.alt_gt_num is None:
            raise ArgumentError('alt_gt_num is required when ignore_alt')
        else:
            args['alt_gt_num'] = parsed_args.alt_gt_num
    args['pre_read_max_size'] = parsed_args.pre_read_max_size
    args['ignore_alt'] = parsed_args.ignore_alt
    args['kept_fields'] = parsed_args.kept_fields
    args['ignored_fields'] = parsed_args.ignored_fields
    return args


def main():
    description = 'Transforms VCF file into HDF5 format'
    parser = _setup_argparse(description=description)
    args = _parse_args(parser)
    vcf_parser = VCFParser(fhand=args['in_fhand'],
                           pre_read_max_size=args['pre_read_max_size'],
                           ignored_fields=args['ignored_fields'],
                           kept_fields=args['kept_fields'],
                           max_field_lens={'alt': args['alt_gt_num']},
                           ignore_alt=args['ignore_alt'])
    h5 = VariationsH5(args['out_fpath'], mode='w')
    h5.put_vars_from_vcf(vcf_parser)


if __name__ == '__main__':
    main()