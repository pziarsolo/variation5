
from collections import defaultdict, Counter

import numpy

from Bio import pairwise2

from variation import (GT_FIELD, CHROM_FIELD, POS_FIELD, REF_FIELD, ALT_FIELD,
                       MISSING_INT, MISSING_STR)
from variation.variations.filters import IndelFilter, FLT_VARS, SELECTED_VARS
from variation.matrix.stats import counts_and_allels_by_row
from variation.gt_writers.vcf import _join_str_array_along_axis0

INDEL_CHAR = b'-'


class AlignmentTooDifficultError(ValueError):
    pass


def _do_easy_multiple_alignment(alleles, lengths):
    longest_allele_idx = numpy.argmax(numpy.array(lengths))
    longest_allele = alleles[longest_allele_idx]

    aligned_alleles = []
    for allele in alleles:
        if allele == longest_allele:
            aligned_allele = allele
        elif not allele.strip():
            aligned_allele == INDEL_CHAR * len(allele)
        else:
            alignment = pairwise2.align.globalxx(longest_allele.decode(),
                                                 allele.decode())[0]
            aligned_allele = alignment[1].encode()
        aligned_alleles.append(aligned_allele)

    # check that this simple multiple alignment is fine
    for idx in range(len(longest_allele)):
        nucleotides = {allele[idx] for allele in aligned_alleles}.difference([45])
        if len(nucleotides) > 1:
            raise AlignmentTooDifficultError('Alignment too difficult')
    return aligned_alleles


def _fix_allele_lengths(alleles, try_to_align_easy_indels,
                        put_hyphens_in_indels):
    if not put_hyphens_in_indels:
        return alleles

    lengths = [len(allele) for allele in alleles]
    one_length = len(alleles[0])
    if all(length == one_length or not length for length in lengths):
        return alleles

    if max(lengths) == 2:
        alleles = [allele + INDEL_CHAR if len(allele) == 1 else allele for allele in alleles]
        return alleles

    if try_to_align_easy_indels:
        alleles = _do_easy_multiple_alignment(alleles, lengths)
    else:
        raise RuntimeError('We should not be here')

    one_length = len(alleles[0])
    if not all([len(allele) == one_length for allele in alleles]):
        raise AlignmentTooDifficultError('Alignment too difficult')

    return alleles


def write_fasta(variations, out_fhand, remove_indels=True,
                write_one_seq_per_sample_setting_hets_to_missing=False,
                remove_invariant_snps=False, remove_sites_all_N=True,
                try_to_align_easy_indels=False, put_hyphens_in_indels=True):

    if not remove_indels:
        if try_to_align_easy_indels and not put_hyphens_in_indels:
            msg = 'try_to_align and not hyphens_in_indels are incompatible options'
            raise ValueError(msg)
        if try_to_align_easy_indels and put_hyphens_in_indels:
            pass
        if not try_to_align_easy_indels and not put_hyphens_in_indels:
            pass
        if not try_to_align_easy_indels and put_hyphens_in_indels:
            msg = 'not try_to_align and put hyphens_in_indels are incompatible options'
            raise ValueError(msg)

    stats = {}
    stats['snps_tried'] = 0
    stats['complex_skipped'] = 0
    stats['snps_written'] = 0

    samples = variations.samples

    chroms = variations[CHROM_FIELD] if CHROM_FIELD in variations else None
    poss = variations[POS_FIELD] if POS_FIELD in variations else None

    if remove_indels:
        filter_indels = IndelFilter(report_selection=True)
        result = filter_indels(variations)
        stats['indels_removed'] = numpy.sum(numpy.logical_not(result[SELECTED_VARS]))
        variations = result[FLT_VARS]
        if chroms is not None:
            chroms = chroms[result['selected_vars']]
        if poss is not None:
            poss = poss[result['selected_vars']]

    N = b'N'
    desc = b''

    if chroms is not None and poss is not None:
        chrom0 = chroms[0].astype('S')
        pos0 = poss[0]
        chrom1 = chroms[-1].astype('S')
        pos1 = poss[-1]
        desc = b' From %s:%i to %s:%i' % (chrom0, pos0, chrom1, pos1)
        if stats is not None:
            stats['start_chrom'] = chrom0
            stats['start_pos'] = chrom0
            stats['end_chrom'] = chrom1
            stats['end_pos'] = chrom1
        if chrom0 == chrom1:
            desc += b' length covered:%i' % (pos1 - pos0)
            if stats is not None:
                stats['length_covered'] = pos1 - pos0

    refs = variations[REF_FIELD]
    alts = variations[ALT_FIELD]
    gts = variations[GT_FIELD][...]

    if write_one_seq_per_sample_setting_hets_to_missing:
        if gts.shape[2] != 2:
            raise NotImplementedError('Not implemented yet for non diploids')

        # remove hets
        haps1 = gts[:, :, 0]
        haps2 = gts[:, :, 1]
        haps1[haps1 != haps2] = MISSING_INT
        shape = haps1.shape
        haplotypes = haps1.reshape((shape[0], shape[1], 1))
        # haps = haps1
    else:
        haplotypes = gts

    if remove_invariant_snps or remove_sites_all_N:
        all_counts, alleles = counts_and_allels_by_row(haplotypes)
        try:
            missing_allele_idx = alleles.index(MISSING_INT)
        except ValueError:
            missing_allele_idx = None
        if missing_allele_idx is None:
            counts = all_counts
            snps_not_all_missing = None
        elif missing_allele_idx == 0:
            counts = all_counts[:, 1:]
            snps_not_all_missing = all_counts[:, missing_allele_idx] < haplotypes.shape[1]
        else:
            raise NotImplementedError('Should be an easy fix')

    haps_to_keep = numpy.ones((haplotypes.shape[0],)) == 1
    if remove_invariant_snps:
        this_haps_to_keep = numpy.sum(counts, axis=1) - numpy.max(counts, axis=1) > 0
        haps_to_keep = numpy.logical_and(haps_to_keep, this_haps_to_keep)

    if remove_sites_all_N and snps_not_all_missing is not None:
        this_haps_to_keep = snps_not_all_missing
        haps_to_keep = numpy.logical_and(haps_to_keep, this_haps_to_keep)

    if haps_to_keep is not None:
        haplotypes = haplotypes[haps_to_keep, ...]
        alts = alts[haps_to_keep]
        refs = refs[haps_to_keep]

    if alts.dtype.itemsize > refs.dtype.itemsize:
        str_dtype = alts.dtype
    else:
        str_dtype = refs.dtype

    letter_haps = numpy.full_like(haplotypes, dtype=str_dtype, fill_value=b'')

    for snp_idx in range(haplotypes.shape[0]):
        stats['snps_tried'] += 1
        alleles = [refs[snp_idx]] + list(alts[snp_idx, :])

        lengths = [len(allele) for allele in alleles]
        len_longest_allele = max(lengths)
        empty_allele = N * len_longest_allele
        letter_haps[snp_idx, :, :] = empty_allele

        try:
            alleles = _fix_allele_lengths(alleles,
                                          try_to_align_easy_indels=try_to_align_easy_indels,
                                          put_hyphens_in_indels=put_hyphens_in_indels)
        except AlignmentTooDifficultError:
            # we don't know how to align this complex, so we skip it
            stats['complex_skipped'] += 1
            continue

        stats['snps_written'] += 1

        ref_allele = alleles[0]
        alt_alleles = alleles[1:]

        letter_haps[snp_idx, :, :][haplotypes[snp_idx, :, :] == 0] = ref_allele
        for alt_allele_idx in range(len(alt_alleles)):
            alt_allele = alt_alleles[alt_allele_idx]
            if alt_allele == MISSING_STR:
                break
            letter_haps[snp_idx, :, :][haplotypes[snp_idx, :, :] == alt_allele_idx + 1] = alt_allele

    joined_letter_haps = []
    for idx in range(letter_haps.shape[2]):
        joined_letter_haps.append(_join_str_array_along_axis0(letter_haps[:, :, idx].T,
                                                              the_str_array_has_newlines=False))

    lengths = []
    for smpl_idx, sample in enumerate(samples):
        for haploid_idx, haploid_joined_letter_haps in enumerate(joined_letter_haps):
            if write_one_seq_per_sample_setting_hets_to_missing:
                this_desc = b'>%s' % sample.encode() + desc
            else:
                this_desc = b'>%s_hap%d' % (sample.encode(), haploid_idx + 1) + desc
            out_fhand.write(this_desc)
            out_fhand.write(b'\n')
            sample_hap = haploid_joined_letter_haps[smpl_idx]
            lengths.append(len(sample_hap))
            out_fhand.write(sample_hap)
            out_fhand.write(b'\n')

    if put_hyphens_in_indels:
        assert all(length == lengths[0] for length in lengths)

    return {'stats': stats}

