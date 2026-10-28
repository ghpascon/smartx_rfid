#include "tm_reader.h"
#include "tmr_serial_reader.h"
#include "tmr_filter.h"
#include "tmr_read_plan.h"
#include "tmr_tag_data.h"
#include "tmr_tagop.h"
#include "tmr_status.h"

#if defined(_WIN32) || defined(WIN32)
#define TMR_DLL_EXPORT __declspec(dllexport)
#else
#define TMR_DLL_EXPORT
#endif

/* Stable, uniquely named exports used by ctypes on Windows. */
TMR_DLL_EXPORT TMR_Status ACUPAD_TMR_create_alloc(TMR_Reader **reader, const char *uri)
{
    return TMR_create_alloc(reader, uri);
}
TMR_DLL_EXPORT TMR_Status ACUPAD_TMR_connect(TMR_Reader *reader)
{
    return TMR_SR_connect(reader);
}
TMR_DLL_EXPORT TMR_Status ACUPAD_TMR_destroy(TMR_Reader *reader)
{
    return TMR_SR_destroy(reader);
}
TMR_DLL_EXPORT TMR_Status ACUPAD_TMR_read(TMR_Reader *reader, uint32_t timeout, int32_t *count)
{
    return TMR_SR_read(reader, timeout, count);
}
TMR_DLL_EXPORT TMR_Status ACUPAD_TMR_hasMoreTags(TMR_Reader *reader)
{
    return TMR_SR_hasMoreTags(reader);
}
TMR_DLL_EXPORT TMR_Status ACUPAD_TMR_getNextTag(TMR_Reader *reader, TMR_TagReadData *data)
{
    return TMR_SR_getNextTag(reader, data);
}
TMR_DLL_EXPORT TMR_Status ACUPAD_TMR_writeTag(TMR_Reader *reader, const TMR_TagFilter *filter, const TMR_TagData *data)
{
    return TMR_SR_writeTag(reader, filter, data);
}
TMR_DLL_EXPORT TMR_Status ACUPAD_TMR_readTagMemBytes(
    TMR_Reader *reader, TMR_TagFilter *filter, uint32_t bank,
    uint32_t address, uint16_t count, uint8_t data[])
{
    return TMR_SR_readTagMemBytes(reader, filter, bank, address, count, data);
}
TMR_DLL_EXPORT TMR_Status ACUPAD_TMR_writeTagMemBytes(
    TMR_Reader *reader, TMR_TagFilter *filter, uint32_t bank,
    uint32_t address, uint16_t count, const uint8_t data[], TMR_uint8List *response)
{
    return TMR_SR_writeTagMemBytes(reader, filter, bank, address, count, data, response);
}
TMR_DLL_EXPORT TMR_Status ACUPAD_TMR_gpoSet(TMR_Reader *reader, uint8_t count, const TMR_GpioPin state[])
{
    return TMR_SR_gpoSet(reader, count, state);
}
TMR_DLL_EXPORT TMR_Status ACUPAD_TMR_paramSet(TMR_Reader *reader, TMR_Param key, const void *value)
{
    return reader->paramSet(reader, key, value);
}
TMR_DLL_EXPORT TMR_Status ACUPAD_TMR_paramGet(TMR_Reader *reader, TMR_Param key, void *value)
{
    return reader->paramGet(reader, key, value);
}
TMR_DLL_EXPORT TMR_Param ACUPAD_TMR_paramID(const char *name)
{
    return TMR_paramID(name);
}
TMR_DLL_EXPORT TMR_Status ACUPAD_TMR_TF_init_gen2_select(
    TMR_TagFilter *filter, bool invert, TMR_GEN2_Bank bank,
    uint32_t bitPointer, uint16_t maskBitLength, uint8_t *mask)
{
    return TMR_TF_init_gen2_select(filter, invert, bank, bitPointer, maskBitLength, mask);
}
TMR_DLL_EXPORT TMR_Status ACUPAD_TMR_RP_init_simple(
    TMR_ReadPlan *plan, uint8_t antennaCount, uint8_t *antennaList,
    TMR_TagProtocol protocol, uint32_t weight)
{
    return TMR_RP_init_simple(plan, antennaCount, antennaList, protocol, weight);
}
TMR_DLL_EXPORT TMR_Status ACUPAD_TMR_TRD_init(TMR_TagReadData *trd)
{
    return TMR_TRD_init(trd);
}
TMR_DLL_EXPORT TMR_Status ACUPAD_TMR_TagOp_init_GEN2_ReadData(
    TMR_TagOp *tagop, TMR_GEN2_Bank bank, uint32_t wordAddress, uint8_t len)
{
    return TMR_TagOp_init_GEN2_ReadData(tagop, bank, wordAddress, len);
}
TMR_DLL_EXPORT const char *ACUPAD_TMR_strerror(TMR_Status status)
{
    return TMR_strerror(status);
}
